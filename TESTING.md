# FSRsync Testing Guide

## Overview

FSRsync includes a comprehensive test suite covering:
- **Unit Tests**: Individual component testing
- **Integration Tests**: Docker-based real sync testing
- **Performance Tests**: Benchmarks and stress tests
- **Scenario Tests**: Real-world use case testing

## Quick Start

### Run All Tests
```bash
./sandbox.sh test-all
```

### Run Specific Test Types

**Unit Tests Only** (fast, no Docker sync):
```bash
./sandbox.sh test-unit
```

**Integration Tests** (Docker-based file sync):
```bash
./sandbox.sh test
```

**Performance Tests**:
```bash
./sandbox.sh test-perf
```

## Test Organization

```
test/
├── test_filesystem_monitor.py  # FilesystemMonitor and File class tests
├── test_web_api.py             # Web API endpoint tests
├── test_integration.py         # Integration and concurrency tests
├── test_sync_scenarios.py      # Real-world sync scenarios
├── test_rsync_manager.py       # RsyncManager tests
└── test_docker_sync.py         # Docker environment validation
```

## Running Tests Locally (Without Docker)

If you have Python and pytest installed locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run all unit tests
pytest test/ -v -m "not integration and not performance"

# Run specific test file
pytest test/test_filesystem_monitor.py -v

# Run specific test
pytest test/test_filesystem_monitor.py::TestFile::test_file_creation -v

# Run with coverage
pytest test/ --cov=fsrsync --cov-report=html
```

## Running Tests in Docker

### Using Docker Compose

**Run all tests in Docker:**
```bash
docker compose -f docker-compose.test.yml run --rm test-server
```

**Run performance tests:**
```bash
docker compose -f docker-compose.test.yml run --rm perf-test
```

### Building and Testing

```bash
# Build test containers
docker compose -f docker-compose.test.yml build

# Run tests
docker compose -f docker-compose.test.yml up test-server

# Cleanup
docker compose -f docker-compose.test.yml down
```

## Test Markers

Tests are organized with pytest markers:

- `@pytest.mark.unit` - Unit tests (fast)
- `@pytest.mark.integration` - Integration tests (require Docker)
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.slow` - Slow-running tests

**Run tests by marker:**
```bash
# Only unit tests
pytest test/ -m unit

# Skip integration tests
pytest test/ -m "not integration"

# Only performance tests
pytest test/ -m performance
```

## Test Coverage

### Current Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| FilesystemMonitor | 20+ | ~90% |
| File class | 5+ | 100% |
| Web API | 15+ | ~85% |
| Integration | 10+ | N/A |
| Sync Scenarios | 15+ | ~80% |
| Performance | 5+ | N/A |

### Generate Coverage Report

```bash
# Run with coverage
pytest test/ --cov=fsrsync --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Writing New Tests

### Unit Test Template

```python
import pytest
from fsrsync.utils.filesystem import FilesystemMonitor, File
from fsrsync.utils.logs import Logger


class TestYourFeature:
    """Test your feature"""

    @pytest.fixture
    def monitor(self):
        return FilesystemMonitor()

    @pytest.fixture
    def logger(self):
        return Logger()

    def test_your_functionality(self, monitor, logger):
        """Test description"""
        # Arrange
        file = File("/test/path.txt", logger)

        # Act
        monitor.add_immediate_sync_file(file)

        # Assert
        files = monitor.get_immediate_sync_files()
        assert len(files) == 1
```

### Integration Test Template

```python
import pytest
import os


@pytest.mark.integration
class TestDockerIntegration:
    """Docker integration tests"""

    def test_sync_functionality(self):
        """Test actual file sync"""
        # Skip if not in Docker
        if not os.path.exists("/root/source"):
            pytest.skip("Not in Docker environment")

        # Your test code here
        assert True
```

## Performance Benchmarks

### Expected Performance

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| Add 1000 files | < 2 seconds | File tracking |
| Retrieve 5000 files | < 1 second | Path filtering |
| Concurrent ops (10 threads) | < 5 seconds | 100 files/thread |

### Running Benchmarks

```bash
# Run all performance tests
pytest test/ -m performance -v

# Run specific performance test
pytest test/test_docker_sync.py::TestPerformance::test_file_tracking_performance -v
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          pytest test/ -v -m "not integration and not performance"

      - name: Run Docker tests
        run: |
          docker compose -f docker-compose.test.yml run --rm test-server
```

## Troubleshooting

### Tests Fail Due to Missing Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt
```

### Tests Timeout in Docker

Increase Docker resource limits:
- Memory: 4GB minimum
- CPUs: 2+ cores recommended

### Permission Issues

```bash
# Fix test directory permissions
chmod -R 755 test/
```

### pytest Not Found

```bash
# Install pytest
pip install pytest pytest-asyncio httpx
```

## Test Data

Test data is created dynamically in tests. No fixture files are required.

### Creating Test Files

```python
import tempfile
import os

# Create temporary directory
tmpdir = tempfile.mkdtemp()

# Create test file
test_file = os.path.join(tmpdir, "test.txt")
with open(test_file, 'w') as f:
    f.write("test content")
```

## Debugging Tests

### Run with Verbose Output

```bash
pytest test/ -vv --tb=long
```

### Run with Print Statements

```bash
pytest test/ -s  # Don't capture stdout
```

### Debug Specific Test

```bash
pytest test/test_filesystem_monitor.py::TestFile::test_file_creation -vv -s
```

### Use pytest Debugger

```python
def test_something():
    import pdb; pdb.set_trace()  # Add breakpoint
    # Your test code
```

## Best Practices

1. **Isolation**: Each test should be independent
2. **Fixtures**: Use fixtures for common setup
3. **Markers**: Tag tests appropriately (unit, integration, performance)
4. **Cleanup**: Always clean up resources (use fixtures with teardown)
5. **Assertions**: Use descriptive assertion messages
6. **Mock External Services**: Mock SSH, rsync when not integration testing

## Common Test Patterns

### Testing Thread Safety

```python
import threading

def test_concurrent_operations():
    monitor = FilesystemMonitor()
    errors = []

    def worker():
        try:
            # Your concurrent operation
            pass
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert len(errors) == 0
```

### Testing File Operations

```python
def test_file_sync():
    monitor = FilesystemMonitor()
    logger = Logger()

    # Add file
    file = File("/test/path.txt", logger)
    monitor.add_immediate_sync_file(file)

    # Verify
    files = monitor.get_immediate_sync_files()
    assert len(files) == 1
    assert files[0].path == "/test/path.txt"

    # Cleanup
    monitor.delete_immediate_sync_file("/test/path.txt")
    assert len(monitor.get_immediate_sync_files()) == 0
```

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [Coverage.py](https://coverage.readthedocs.io/)

## Support

For test-related issues:
1. Check this guide
2. Review test output carefully
3. Run with `-vv --tb=long` for detailed errors
4. Check Docker logs if integration tests fail
