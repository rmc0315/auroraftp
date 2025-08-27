"""Transfer queue management and execution."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from uuid import UUID

from ..core.events import event_bus
from ..core.models import TransferDirection, TransferItem, TransferStatus
from ..protocols import ProtocolFactory, ProtocolSession

logger = logging.getLogger(__name__)


class TransferWorker:
    """Individual transfer worker."""
    
    def __init__(self, worker_id: int, manager: "TransferManager"):
        self.worker_id = worker_id
        self.manager = manager
        self.current_transfer: Optional[TransferItem] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def start(self) -> None:
        """Start the worker."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._worker_loop())
    
    async def stop(self) -> None:
        """Stop the worker."""
        self._stop_event.set()
        if self._task:
            await self._task
    
    async def _worker_loop(self) -> None:
        """Main worker loop."""
        while not self._stop_event.is_set():
            try:
                # Get next transfer from queue
                transfer = await self.manager.get_next_transfer()
                if not transfer:
                    await asyncio.sleep(1)
                    continue
                
                self.current_transfer = transfer
                await self._execute_transfer(transfer)
                
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                if self.current_transfer:
                    await self.manager.mark_transfer_failed(
                        self.current_transfer.id,
                        str(e)
                    )
            finally:
                self.current_transfer = None
    
    async def _execute_transfer(self, transfer: TransferItem) -> None:
        """Execute a single transfer."""
        try:
            # Mark transfer as started
            await self.manager.mark_transfer_started(transfer.id)
            
            # Get session for this transfer
            session = await self.manager.get_session(transfer.site_id)
            if not session:
                raise Exception("Failed to get session")
            
            # Create progress callback
            def progress_callback(transferred: int, total: int) -> None:
                self.manager.update_transfer_progress(transfer.id, transferred, total)
            
            # Execute transfer based on direction
            if transfer.direction == TransferDirection.DOWNLOAD:
                await session.download(
                    transfer.remote_path,
                    transfer.local_path,
                    progress_callback=progress_callback,
                )
            else:  # UPLOAD
                await session.upload(
                    transfer.local_path,
                    transfer.remote_path,
                    progress_callback=progress_callback,
                )
            
            # Mark as completed
            await self.manager.mark_transfer_completed(transfer.id)
            
        except Exception as e:
            logger.error(f"Transfer {transfer.id} failed: {e}")
            await self.manager.mark_transfer_failed(transfer.id, str(e))


class TransferManager:
    """Manages transfer queue and workers."""
    
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.transfers: Dict[UUID, TransferItem] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: List[TransferWorker] = []
        self.sessions: Dict[UUID, ProtocolSession] = {}
        self.paused_transfers: Set[UUID] = set()
        self._running = False
    
    async def start(self) -> None:
        """Start the transfer manager."""
        if self._running:
            return
        
        self._running = True
        
        # Create and start workers
        for i in range(self.max_workers):
            worker = TransferWorker(i, self)
            self.workers.append(worker)
            await worker.start()
        
        event_bus.queue_started.emit()
        logger.info(f"Transfer manager started with {self.max_workers} workers")
    
    async def stop(self) -> None:
        """Stop the transfer manager."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop all workers
        for worker in self.workers:
            await worker.stop()
        
        self.workers.clear()
        
        # Close all sessions
        for session in self.sessions.values():
            try:
                await session.disconnect()
            except Exception:
                pass
        
        self.sessions.clear()
        
        event_bus.queue_paused.emit()
        logger.info("Transfer manager stopped")
    
    def add_transfer(self, transfer: TransferItem) -> None:
        """Add transfer to queue."""
        self.transfers[transfer.id] = transfer
        
        # Add to queue if not paused
        if transfer.id not in self.paused_transfers:
            try:
                self.queue.put_nowait(transfer.id)
            except asyncio.QueueFull:
                logger.warning("Transfer queue is full")
        
        event_bus.transfer_added.emit(transfer.id)
        logger.info(f"Added transfer: {transfer.local_path} <-> {transfer.remote_path}")
    
    def remove_transfer(self, transfer_id: UUID) -> None:
        """Remove transfer from queue."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            
            # Cancel if running
            if transfer.status == TransferStatus.RUNNING:
                transfer.status = TransferStatus.CANCELLED
                event_bus.transfer_cancelled.emit(transfer_id)
            
            del self.transfers[transfer_id]
            self.paused_transfers.discard(transfer_id)
    
    def pause_transfer(self, transfer_id: UUID) -> None:
        """Pause a transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == TransferStatus.PENDING:
                transfer.status = TransferStatus.PAUSED
                self.paused_transfers.add(transfer_id)
                event_bus.transfer_paused.emit(transfer_id)
    
    def resume_transfer(self, transfer_id: UUID) -> None:
        """Resume a paused transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == TransferStatus.PAUSED:
                transfer.status = TransferStatus.PENDING
                self.paused_transfers.discard(transfer_id)
                
                # Add back to queue
                try:
                    self.queue.put_nowait(transfer_id)
                except asyncio.QueueFull:
                    logger.warning("Transfer queue is full")
                
                event_bus.transfer_resumed.emit(transfer_id)
    
    def retry_transfer(self, transfer_id: UUID) -> None:
        """Retry a failed transfer."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            if transfer.status == TransferStatus.FAILED and transfer.can_retry:
                transfer.status = TransferStatus.PENDING
                transfer.retry_count += 1
                transfer.error_message = None
                transfer.transferred = 0
                
                # Add back to queue
                try:
                    self.queue.put_nowait(transfer_id)
                except asyncio.QueueFull:
                    logger.warning("Transfer queue is full")
    
    def clear_completed(self) -> None:
        """Remove all completed transfers."""
        completed_ids = [
            transfer_id for transfer_id, transfer in self.transfers.items()
            if transfer.status in [TransferStatus.COMPLETED, TransferStatus.CANCELLED]
        ]
        
        for transfer_id in completed_ids:
            del self.transfers[transfer_id]
        
        event_bus.queue_cleared.emit()
    
    async def get_next_transfer(self) -> Optional[TransferItem]:
        """Get next transfer from queue."""
        try:
            transfer_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            return self.transfers.get(transfer_id)
        except asyncio.TimeoutError:
            return None
    
    async def get_session(self, site_id: UUID) -> Optional[ProtocolSession]:
        """Get or create session for site."""
        if site_id in self.sessions:
            session = self.sessions[site_id]
            if session.is_connected:
                return session
        
        # Create new session
        from ..core.config import get_config_manager
        config_manager = get_config_manager()
        site = config_manager.get_site(site_id)
        
        if not site:
            logger.error(f"Site {site_id} not found")
            return None
        
        try:
            session = ProtocolFactory.create_session(site)
            await session.connect()
            self.sessions[site_id] = session
            return session
        except Exception as e:
            logger.error(f"Failed to create session for {site_id}: {e}")
            return None
    
    async def mark_transfer_started(self, transfer_id: UUID) -> None:
        """Mark transfer as started."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = TransferStatus.RUNNING
            transfer.started_at = datetime.utcnow()
            event_bus.transfer_started.emit(transfer_id)
    
    async def mark_transfer_completed(self, transfer_id: UUID) -> None:
        """Mark transfer as completed."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = datetime.utcnow()
            transfer.transferred = transfer.size
            event_bus.transfer_completed.emit(transfer_id)
    
    async def mark_transfer_failed(self, transfer_id: UUID, error: str) -> None:
        """Mark transfer as failed."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.status = TransferStatus.FAILED
            transfer.error_message = error
            event_bus.transfer_failed.emit(transfer_id, error)
    
    def update_transfer_progress(self, transfer_id: UUID, transferred: int, total: int) -> None:
        """Update transfer progress."""
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            transfer.transferred = transferred
            if total > 0:
                transfer.size = total
            event_bus.transfer_progress.emit(transfer_id, transferred, total)
    
    def get_transfer(self, transfer_id: UUID) -> Optional[TransferItem]:
        """Get transfer by ID."""
        return self.transfers.get(transfer_id)
    
    def get_all_transfers(self) -> List[TransferItem]:
        """Get all transfers."""
        return list(self.transfers.values())
    
    def get_active_transfers(self) -> List[TransferItem]:
        """Get active (running/pending) transfers."""
        return [
            transfer for transfer in self.transfers.values()
            if transfer.status in [TransferStatus.PENDING, TransferStatus.RUNNING]
        ]
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        stats = {
            "total": len(self.transfers),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "paused": 0,
            "cancelled": 0,
        }
        
        for transfer in self.transfers.values():
            if transfer.status == TransferStatus.PENDING:
                stats["pending"] += 1
            elif transfer.status == TransferStatus.RUNNING:
                stats["running"] += 1
            elif transfer.status == TransferStatus.COMPLETED:
                stats["completed"] += 1
            elif transfer.status == TransferStatus.FAILED:
                stats["failed"] += 1
            elif transfer.status == TransferStatus.PAUSED:
                stats["paused"] += 1
            elif transfer.status == TransferStatus.CANCELLED:
                stats["cancelled"] += 1
        
        return stats