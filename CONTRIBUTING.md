# Contributing to AuroraFTP

Thank you for your interest in contributing to AuroraFTP! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Qt6 development libraries
- OpenSSH client
- Docker (for integration tests)

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3.11 python3-pip python3-venv libqt6-widgets6 libqt6-core6 openssh-client
```

### Development Environment

1. Clone the repository:
```bash
git clone https://github.com/rmc0315/auroraftp.git
cd auroraftp
```

2. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install development dependencies:
```bash
pip install -e ".[dev,test]"
```

4. Install pre-commit hooks:
```bash
pre-commit install
```

## Development Workflow

### Running in Development Mode

```bash
./scripts/run_dev.sh
```

This script:
- Checks for required dependencies
- Sets up development environment variables
- Runs AuroraFTP with debug logging

### Running Tests

```bash
# Unit tests only
pytest tests/unit

# All tests including integration (requires Docker)
./scripts/run_tests.sh --integration --coverage

# Specific test file
pytest tests/unit/test_models.py -v
```

### Code Quality

We use several tools to maintain code quality:

- **ruff**: Fast Python linter and formatter
- **black**: Code formatter
- **mypy**: Type checking
- **pre-commit**: Git hooks for automated checks

Run quality checks:
```bash
# Lint and format
ruff check auroraftp/
ruff format auroraftp/

# Type checking
mypy auroraftp/

# Run all pre-commit hooks
pre-commit run --all-files
```

## Project Structure

```
auroraftp/
├── app.py                    # Main application entry point
├── core/                     # Core models and configuration
│   ├── models.py            # Data models
│   ├── config.py            # Configuration management
│   └── events.py            # Event system
├── protocols/               # Protocol implementations
│   ├── base.py             # Abstract protocol interface
│   ├── ftp_async.py        # FTP/FTPS implementation
│   ├── sftp_async.py       # SFTP implementation
│   └── autodetect.py       # URL parsing
├── services/               # Business logic services
│   ├── transfer_manager.py # Transfer queue management
│   ├── sync_engine.py      # Folder synchronization
│   └── logging.py          # Logging configuration
├── widgets/                # UI components
│   ├── main_window.py      # Main application window
│   ├── connection_tab.py   # Connection tabs
│   ├── file_pane.py        # File browser panes
│   ├── site_manager.py     # Site management dialog
│   ├── transfer_queue.py   # Transfer queue widget
│   └── log_panel.py        # Log display panel
└── tests/                  # Test suite
    ├── unit/               # Unit tests
    └── integration/        # Integration tests
```

## Coding Guidelines

### Python Style

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Maximum line length: 88 characters (Black default)
- Use descriptive variable and function names
- Add docstrings for all public functions and classes

### Qt/PyQt6 Guidelines

- Use Qt's signals and slots for communication between components
- Avoid direct widget manipulation from non-UI threads
- Use `asyncio` for asynchronous operations
- Keep UI updates on the main thread

### Architecture Principles

- **Separation of Concerns**: Keep UI, business logic, and data access separate
- **Async First**: Use `asyncio` for all I/O operations
- **Event-Driven**: Use the event bus for inter-component communication
- **Testable**: Write code that can be easily unit tested
- **Secure**: Never log or store credentials in plaintext

## Adding New Features

### Protocol Support

To add a new protocol:

1. Create a new file in `auroraftp/protocols/`
2. Implement the `ProtocolSession` interface
3. Register the protocol with `ProtocolFactory`
4. Add appropriate tests
5. Update documentation

### UI Components

For new UI components:

1. Create widget in `auroraftp/widgets/`
2. Follow existing patterns for signals/slots
3. Add to `__init__.py` for imports
4. Write Qt-specific tests using `pytest-qt`

### Services

For business logic:

1. Add to `auroraftp/services/`
2. Use dependency injection where possible
3. Emit events for state changes
4. Write comprehensive unit tests

## Testing

### Unit Tests

- Test all business logic thoroughly
- Mock external dependencies
- Use fixtures for common test data
- Aim for >90% code coverage

### Integration Tests

- Test real protocol implementations
- Use Docker containers for test servers
- Test error conditions and edge cases
- Verify security features

### UI Tests

- Use `pytest-qt` for Qt widget testing
- Test user interactions and workflows
- Mock backend services when appropriate

## Documentation

### Code Documentation

- Add docstrings to all public APIs
- Use Google-style docstrings
- Include type information in docstrings
- Add inline comments for complex logic

### User Documentation

- Update README.md for new features
- Add screenshots for UI changes
- Document configuration options
- Provide troubleshooting guides

## Security Considerations

### Credential Handling

- Never log passwords or private keys
- Use secure storage (keyring) when possible
- Implement secure fallback (encrypted storage)
- Clear sensitive data from memory

### Network Security

- Validate SSL certificates by default
- Support modern TLS versions
- Implement proper SSH host key verification
- Handle authentication errors securely

## Submitting Changes

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation as needed
7. Commit with descriptive messages
8. Push to your fork
9. Open a Pull Request

### Commit Messages

Use conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Maintenance tasks

Examples:
```
feat(protocols): add FTPS implicit TLS support

fix(ui): resolve file pane refresh issue when connection drops

docs(readme): update installation instructions for Ubuntu 22.04
```

### Code Review

All pull requests require:
- At least one code review approval
- All CI checks passing
- No merge conflicts
- Updated tests and documentation

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release PR
4. Tag release after merge
5. GitHub Actions builds packages automatically

## Getting Help

- Open an issue for bugs or feature requests
- Join discussions for questions and ideas
- Check existing issues and PRs before submitting
- Provide minimal reproduction cases for bugs

## Recognition

Contributors are recognized in:
- CHANGELOG.md for each release
- GitHub contributors list
- Special thanks in major releases

Thank you for contributing to AuroraFTP!