"""Main application entry point."""

import asyncio
import logging
import sys
from pathlib import Path

import click
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from .core.config import get_config_manager
from .services import setup_logging
from .widgets.main_window import MainWindow


def setup_qt_event_loop() -> None:
    """Setup Qt event loop to work with asyncio."""
    import qasync
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    return app, loop


@click.command()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--config-dir", type=click.Path(), help="Override config directory")
@click.option("--connect", help="Auto-connect to URL (sftp://user@host:port)")
@click.option("--password-env", help="Environment variable containing password")
@click.option("--remote", help="Remote directory to navigate to")
@click.option("--download", type=click.Path(), help="Download remote files to local directory")
@click.option("--upload", type=click.Path(exists=True), help="Upload local files to remote directory")
@click.option("--sync-profile", help="Execute sync profile by name")
@click.option("--dry-run", is_flag=True, help="Perform dry run (with --sync-profile)")
def main(
    debug: bool = False,
    config_dir: str = None,
    connect: str = None,
    password_env: str = None,
    remote: str = None,
    download: str = None,
    upload: str = None,
    sync_profile: str = None,
    dry_run: bool = False,
) -> None:
    """AuroraFTP - Modern FTP/SFTP client."""
    
    # Setup logging
    log_level = "DEBUG" if debug else "INFO"
    setup_logging(level=log_level)
    
    logger = logging.getLogger("auroraftp.app")
    logger.info("Starting AuroraFTP")
    
    # Load configuration
    config_manager = get_config_manager()
    config = config_manager.load_config()
    
    # Handle CLI-only operations
    if any([connect, sync_profile]):
        return run_headless(
            connect=connect,
            password_env=password_env,
            remote=remote,
            download=download,
            upload=upload,
            sync_profile=sync_profile,
            dry_run=dry_run,
        )
    
    # Setup Qt application
    try:
        import qasync
    except ImportError:
        logger.error("qasync is required for GUI mode. Install with: pip install qasync")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    app.setApplicationName("AuroraFTP")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("AuroraFTP")
    
    # Setup event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Create main window
    main_window = MainWindow()
    main_window.show()
    
    # Auto-connect if specified
    if connect:
        QTimer.singleShot(100, lambda: main_window.auto_connect(connect, password_env))
    
    # Run application
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    finally:
        logger.info("AuroraFTP shutdown complete")


def run_headless(
    connect: str = None,
    password_env: str = None,
    remote: str = None,
    download: str = None,
    upload: str = None,
    sync_profile: str = None,
    dry_run: bool = False,
) -> None:
    """Run headless operations."""
    import os
    from .protocols import ProtocolFactory, URLParser
    from .services import TransferManager, SyncEngine
    
    logger = logging.getLogger("auroraftp.headless")
    
    async def run_operations():
        try:
            if sync_profile:
                await run_sync_profile(sync_profile, dry_run)
            elif connect:
                await run_connect_operations(
                    connect, password_env, remote, download, upload
                )
        except Exception as e:
            logger.error(f"Operation failed: {e}")
            sys.exit(1)
    
    async def run_sync_profile(profile_name: str, dry_run: bool):
        config_manager = get_config_manager()
        profiles = config_manager.load_sync_profiles()
        
        profile = None
        for p in profiles.values():
            if p.name == profile_name:
                profile = p
                break
        
        if not profile:
            raise ValueError(f"Sync profile '{profile_name}' not found")
        
        # Get site
        site = config_manager.get_site(profile.site_id)
        if not site:
            raise ValueError(f"Site for profile '{profile_name}' not found")
        
        # Connect and sync
        session = ProtocolFactory.create_session(site)
        async with session.session():
            sync_engine = SyncEngine()
            
            if dry_run:
                profile.dry_run = True
            
            result = await sync_engine.execute_sync(profile, session)
            
            logger.info(f"Sync completed: {result.success_count} actions, {result.error_count} errors")
            for action in result.actions_planned:
                status = "✓" if action in result.actions_executed else "✗"
                logger.info(f"{status} {action}")
    
    async def run_connect_operations(
        url: str,
        password_env: str,
        remote_dir: str,
        download_dir: str,
        upload_path: str,
    ):
        # Parse URL
        site = URLParser.parse_url(url)
        if not site:
            raise ValueError(f"Invalid URL: {url}")
        
        # Set password from environment
        if password_env:
            password = os.getenv(password_env)
            if password:
                site.credential.password = password
        
        # Connect
        session = ProtocolFactory.create_session(site)
        async with session.session():
            logger.info(f"Connected to {site.hostname}")
            
            # Navigate to remote directory
            if remote_dir:
                await session.change_directory(remote_dir)
                logger.info(f"Changed to remote directory: {remote_dir}")
            
            # Download operations
            if download_dir:
                download_path = Path(download_dir)
                download_path.mkdir(parents=True, exist_ok=True)
                
                files = await session.list_directory(".")
                for file in files:
                    if not file.is_directory:
                        local_file = download_path / file.name
                        await session.download(file.path, local_file)
                        logger.info(f"Downloaded: {file.path} -> {local_file}")
            
            # Upload operations
            if upload_path:
                upload_path = Path(upload_path)
                if upload_path.is_file():
                    await session.upload(upload_path, upload_path.name)
                    logger.info(f"Uploaded: {upload_path} -> {upload_path.name}")
                elif upload_path.is_dir():
                    for file_path in upload_path.rglob("*"):
                        if file_path.is_file():
                            rel_path = file_path.relative_to(upload_path)
                            await session.upload(file_path, str(rel_path))
                            logger.info(f"Uploaded: {file_path} -> {rel_path}")
    
    # Run async operations
    asyncio.run(run_operations())


if __name__ == "__main__":
    main()