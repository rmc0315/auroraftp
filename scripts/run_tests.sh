#!/bin/bash
# Test runner script for AuroraFTP

set -e

# Check if we're in a virtual environment
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo "Warning: Not in a virtual environment"
fi

# Check if running from project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: Must run from project root directory"
    exit 1
fi

# Install test dependencies
echo "Installing test dependencies..."
pip install -e ".[test]"

# Function to check if Docker is available and running
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Docker not found. Integration tests will be skipped."
        return 1
    fi
    
    if ! docker info &> /dev/null; then
        echo "Docker daemon not running. Integration tests will be skipped."
        return 1
    fi
    
    return 0
}

# Function to start test services
start_test_services() {
    echo "Starting test services with Docker Compose..."
    cd tests/integration
    
    # Pull images
    docker-compose pull
    
    # Start services
    docker-compose up -d
    
    # Wait for services to be healthy
    echo "Waiting for services to be ready..."
    for service in sftp ftp openssh ftps; do
        echo -n "Waiting for $service... "
        timeout=60
        while [ $timeout -gt 0 ]; do
            if docker-compose ps --services --filter status=running | grep -q "^$service$"; then
                if docker-compose exec -T "$service" echo "ok" &>/dev/null; then
                    echo "ready"
                    break
                fi
            fi
            sleep 2
            timeout=$((timeout - 2))
        done
        
        if [ $timeout -le 0 ]; then
            echo "failed (timeout)"
        fi
    done
    
    cd ../..
}

# Function to stop test services
stop_test_services() {
    echo "Stopping test services..."
    cd tests/integration
    docker-compose down -v
    cd ../..
}

# Parse command line arguments
RUN_INTEGRATION=false
COVERAGE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --integration)
            RUN_INTEGRATION=true
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --integration    Run integration tests (requires Docker)"
            echo "  --coverage       Generate coverage report"
            echo "  --verbose        Verbose output"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Setup pytest arguments
PYTEST_ARGS=()

if [[ "$VERBOSE" == "true" ]]; then
    PYTEST_ARGS+=("-v")
fi

if [[ "$COVERAGE" == "true" ]]; then
    PYTEST_ARGS+=("--cov=auroraftp" "--cov-report=html" "--cov-report=term-missing")
fi

# Run unit tests
echo "Running unit tests..."
pytest tests/unit "${PYTEST_ARGS[@]}"

# Run integration tests if requested
if [[ "$RUN_INTEGRATION" == "true" ]]; then
    if check_docker; then
        # Start test services
        start_test_services
        
        # Trap to ensure cleanup
        trap stop_test_services EXIT
        
        echo "Running integration tests..."
        pytest tests/integration -m integration "${PYTEST_ARGS[@]}"
        
        # Stop services (also called by trap)
        stop_test_services
    else
        echo "Skipping integration tests (Docker not available)"
        exit 1
    fi
fi

echo "Tests completed successfully!"

if [[ "$COVERAGE" == "true" ]]; then
    echo "Coverage report generated in htmlcov/"
fi