# Technical Decisions and Implementation Details

## Architecture Decisions

### 1. Async/Await Throughout
**Decision**: Use Python's asyncio for all I/O operations
**Rationale**: 
- Natural fit for I/O-bound distributed systems
- Efficient handling of concurrent jobs
- Built-in support in aiohttp
- Simpler than threading for this use case

### 2. Plugin Architecture
**Decision**: Decorator-based plugin registration
**Implementation**:
```python
@op("sum")
async def handle(job: Job):
    return {"result": job.payload["a"] + job.payload["b"]}
```
**Benefits**:
- Easy to add new operations
- Clear separation between framework and business logic
- Hot-swappable in theory (with proper reload mechanism)

### 3. Outbox Pattern
**Decision**: JSONL file-based outbox for failed reports
**Trade-offs**:
- ✓ Simple implementation
- ✓ Crash-resistant
- ✓ No external dependencies
- ✗ Not suitable for high-throughput scenarios
- ✗ No built-in rotation

**Future**: Could migrate to SQLite or Redis for production

### 4. Configuration Management
**Decision**: Environment variables with dataclass
**Benefits**:
- 12-factor app compliance
- Type safety with frozen dataclasses
- Clear defaults
- Easy testing with patch.dict

### 5. Identity Management
**Decision**: Machine fingerprint + UUID instance ID
**Components**:
- Machine fingerprint: SHA256(hostname|platform)
- Instance ID: Random UUID per process
- Persistent storage in JSON file

**Rationale**: Allows tracking both physical machines and process instances

## Implementation Challenges and Solutions

### Challenge 1: Async Context Manager Mocking
**Problem**: Tests were failing with "coroutine was never awaited" warnings
**Solution**: Created proper async context manager mocks
```python
def create_async_context_manager(return_value):
    async_cm = AsyncMock()
    async_cm.__aenter__.return_value = return_value
    async_cm.__aexit__.return_value = None
    return async_cm
```

### Challenge 2: Job Handler Registry in Tests
**Problem**: Tests couldn't find job handlers because plugins weren't loaded
**Solution**: Created a fixture to mock the registry
```python
@pytest.fixture
def mock_job_registry():
    from bot.jobs import REGISTRY
    original = REGISTRY.copy()
    REGISTRY.clear()
    REGISTRY["sum"] = AsyncMock(return_value={"result": 42})
    yield REGISTRY
    REGISTRY.clear()
    REGISTRY.update(original)
```

### Challenge 3: Report Failure Handling
**Problem**: Network errors during success reporting were treated as job failures
**Initial Code**:
```python
try:
    result = await run_job(job)
    await self.api.report(job.id, "complete", payload)
except Exception as e:
    # Everything treated as job failure
```

**Fixed Code**:
```python
try:
    result = await run_job(job)
except Exception as e:
    # Job execution failed
else:
    # Job succeeded, try to report
    try:
        await self.api.report(job.id, "complete", payload)
    except Exception:
        # Report failed, but job succeeded
        outbox.append({"action": "complete", ...})
```

### Challenge 4: Platform-Specific File Permissions
**Problem**: Unix file permission tests failing on Windows
**Solution**: Platform detection
```python
if platform.system() != 'Windows':
    assert not (mode & st.S_IRGRP)  # No group read
```

## Testing Strategy

### Test Pyramid
1. **Unit Tests** (60 tests)
   - Fast, isolated, mocked dependencies
   - Focus on single component behavior
   
2. **Integration Tests** (10 tests)
   - Multiple components working together
   - Real implementations where sensible
   
3. **Contract Tests** (8 tests)
   - API schema validation
   - Prevents drift between bot and server
   
4. **E2E Tests** (3 tests)
   - Full system with mock HTTP server
   - Tests complete workflows
   
5. **Performance Tests** (5 tests)
   - Throughput benchmarks
   - Memory leak detection
   - Concurrency validation

### Key Testing Patterns

#### Async Test Pattern
```python
@pytest.mark.asyncio
async def test_something():
    result = await async_function()
    assert result == expected
```

#### Mock Side Effects Pattern
```python
responses_iter = iter([response1, response2, Exception()])
mock.side_effect = lambda *args: next(responses_iter)
```

#### Temp Directory Pattern
```python
def test_with_files(temp_state_dir):
    test_file = temp_state_dir / "test.json"
    # Automatically cleaned up
```

## Performance Considerations

### Concurrency Control
- Semaphore-based limiting prevents resource exhaustion
- Default max_concurrency = 2 (configurable)
- Graceful handling when limit reached

### Connection Pooling
- aiohttp ClientSession reused across requests
- Single session per bot instance
- Configurable timeout (30s default)

### Outbox Performance
- Append: O(1) - just writes to end of file
- Drain: O(n) - reads entire file
- Trade-off: Simple implementation vs. performance
- Benchmark: 1000 items write in <500ms, read in <100ms

### Job Processing Throughput
- Benchmark: >50 jobs/second with concurrency
- Limited by network I/O, not CPU
- Plugin handlers should be async-aware

## Security Considerations

### Authentication
- Bearer token stored in ApiClient
- Token obtained during registration
- TODO: Token refresh mechanism

### Identity Security
- Identity file created with user-only permissions (Unix)
- Machine fingerprint doesn't include sensitive data
- Instance ID rotatable without losing bot identity

### Configuration Security
- Sensitive values from environment variables
- No hardcoded credentials
- Settings frozen after initialization

## Monitoring and Observability

### Current State
- Basic logging setup prepared
- Heartbeat mechanism for liveness
- Job success/failure tracking

### Future Enhancements
1. Structured logging with correlation IDs
2. Metrics export (Prometheus format)
3. Distributed tracing (OpenTelemetry)
4. Health check endpoint
5. Debug mode with detailed logging

## Deployment Considerations

### Process Management
- Single long-running process
- Graceful shutdown on SIGTERM (designed, not fully implemented)
- State persistence across restarts

### Scaling Strategy
- Horizontal scaling: Multiple bot instances
- Work distribution: Server-side queue assignment
- No direct bot-to-bot communication needed

### Failure Recovery
- Automatic reconnection on network errors
- Job lease expiration for crash recovery
- Outbox ensures no lost reports
- Identity persistence across restarts

## Code Organization

### Package Structure Rationale
- `bot/`: Core implementation
- `bot/plugins/`: Extensible operations
- `bin/`: Entry points
- `tests/`: Comprehensive test suite
- `journals/`: Documentation

### Import Strategy
- Relative imports within bot package
- Type hints throughout
- Minimal external dependencies

### Naming Conventions
- Async functions: No special prefix (all I/O is async)
- Private methods: Leading underscore
- Constants: UPPERCASE
- Classes: PascalCase
- Functions/variables: snake_case