# Bot Test Suite

Comprehensive test coverage for the distributed system bot, organized by test type and scope.

## Test Structure

```
tests/
├── unit/           # Pure unit tests (mocked dependencies)
├── integration/    # Multi-component tests
├── contract/       # API schema validation
├── e2e/           # End-to-end with mock server
├── perf/          # Performance benchmarks
└── fixtures/      # Test data files
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific test type
pytest tests/unit/
pytest tests/integration/
pytest -m "not slow"  # Skip slow tests

# Run with coverage
pytest --cov=bot --cov-report=html

# Run performance tests
pytest tests/perf/ -v

# Run specific test file
pytest tests/unit/test_settings.py

# Run with parallel execution
pytest -n auto
```

## Test Categories

### Unit Tests
- **Isolated**: Test individual components with mocked dependencies
- **Fast**: Sub-millisecond execution
- **Coverage**: Each module has corresponding test file
- **Examples**: 
  - `test_settings.py`: Configuration loading
  - `test_identity.py`: Bot identity management
  - `test_scheduler.py`: Job scheduling logic

### Integration Tests
- **Multi-component**: Test interactions between modules
- **Realistic**: Use real implementations where possible
- **Examples**:
  - `test_end_to_end_flow.py`: Complete job processing flow
  - Network failure recovery scenarios
  - Assignment update handling

### Contract Tests
- **API validation**: Ensure requests/responses match schemas
- **Backwards compatibility**: Detect breaking changes
- **JSON Schema**: Validates structure and types
- **Examples**:
  - Register request/response validation
  - Heartbeat format checking
  - Job claim/report schemas

### E2E Tests
- **Full system**: Bot against mock HTTP server
- **Realistic scenarios**: Network issues, concurrent bots
- **In-process server**: Uses aiohttp test utilities
- **Examples**:
  - Happy path job processing
  - Network flap recovery
  - Multiple bot coordination

### Performance Tests
- **Benchmarks**: Measure throughput and latency
- **Concurrency**: Test parallel processing limits
- **Memory**: Check for leaks during long runs
- **Metrics**:
  - Job processing throughput (>50 jobs/sec)
  - Outbox write/read performance
  - API connection pooling efficiency

## Key Test Patterns

### Async Testing
```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_func()
    assert result == expected
```

### Mocking API Calls
```python
bot.api = AsyncMock(spec=ApiClient)
bot.api.claim.return_value = [{"id": "job_1", ...}]
```

### Temp File Handling
```python
def test_with_files(temp_state_dir):
    test_file = temp_state_dir / "test.json"
    # temp_state_dir is auto-cleaned after test
```

### Time-based Testing
```python
with patch('time.time', return_value=1234567890):
    # Test with fixed time
```

## Coverage Goals

- **Unit**: 90%+ coverage of business logic
- **Integration**: Key workflows covered
- **E2E**: Critical user paths tested
- **Overall**: 80%+ total coverage

## Test Data

The `fixtures/` directory contains:
- Sample API responses
- Test job payloads
- Mock configuration files

## Debugging Tests

```bash
# Run with verbose output
pytest -vv

# Drop into debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Run specific test by name
pytest -k "test_claim_throughput"
```

## CI/CD Integration

Tests are designed to run in CI with:
- No external dependencies required
- Deterministic results (no timing-based flakiness)
- Parallel execution support
- Clear failure messages