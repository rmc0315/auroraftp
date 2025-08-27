#!/bin/bash
# Development runner script for AuroraFTP

set -e

# Check if we're in a virtual environment
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "Warning: Not in a virtual environment"
    echo "Consider running: python -m venv venv && source venv/bin/activate"
fi

# Check if running from project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Install dependencies in development mode if needed
if [[ ! -f ".dev_installed" ]]; then
    echo "Installing development dependencies..."
    pip install -e ".[dev]"
    touch .dev_installed
fi

# Check for required system dependencies
echo "Checking system dependencies..."

# Check for Qt6
if ! python -c "import PyQt6" 2>/dev/null; then
    echo "Error: PyQt6 not available. Install Qt6 development packages:"
    echo "  Ubuntu/Debian: sudo apt install python3-pyqt6 python3-pyqt6-dev"
    echo "  Or install via pip: pip install PyQt6"
    exit 1
fi

# Check for qasync
if ! python -c "import qasync" 2>/dev/null; then
    echo "Installing qasync for async Qt support..."
    pip install qasync
fi

# Set development environment variables
export AURORAFTP_ENV=development
export AURORAFTP_DEBUG=1

# Create log directory
mkdir -p logs

echo "Starting AuroraFTP in development mode..."
echo "Press Ctrl+C to stop"

# Run with debug logging
python -m auroraftp.app --debug "$@"