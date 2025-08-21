import pytest
import asyncio
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch
import json
import tempfile
import pathlib
from datetime import datetime, timedelta

# Shared fixtures for all tests

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_identity():
    return {
        "bot_key": "test-machine-fingerprint",
        "instance_id": "test-uuid-1234",
        "hostname": "test-host",
        "os": "test-platform"
    }

@pytest.fixture
def mock_api_client():
    client = AsyncMock()
    client._token = "test-token"
    client.register = AsyncMock()
    client.heartbeat = AsyncMock()
    client.claim = AsyncMock()
    client.report = AsyncMock()
    return client

@pytest.fixture
def temp_state_dir(tmp_path):
    """Create a temporary directory for state files."""
    state_dir = tmp_path / ".state"
    state_dir.mkdir()
    return state_dir

@pytest.fixture
def mock_job():
    return {
        "id": "job_123",
        "op": "sum",
        "payload": {"a": 5, "b": 3},
        "lease_until": (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    }

@pytest.fixture
def mock_assignment():
    return {
        "operations": ["sum", "subtract"],
        "max_concurrency": 2,
        "paused": False
    }

@pytest.fixture
def mock_register_response(mock_assignment):
    return {
        "bot_id": "bot_abc123",
        "auth": {"access_token": "token_xyz"},
        "assignment": mock_assignment,
        "config": {
            "heartbeat_interval": 30,
            "claim_batch_size": 5
        }
    }

@pytest.fixture
async def mock_session():
    """Mock aiohttp session."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    response = AsyncMock()
    response.status = 200
    response.json = AsyncMock(return_value={})
    session.post = AsyncMock(return_value=response)
    session.put = AsyncMock(return_value=response)
    return session

@pytest.fixture
def mock_job_registry():
    """Set up a mock job registry for tests."""
    from bot.jobs import REGISTRY
    # Save original registry
    original = REGISTRY.copy()
    # Clear and add test handler
    REGISTRY.clear()
    REGISTRY["sum"] = AsyncMock(return_value={"result": 42})
    yield REGISTRY
    # Restore original
    REGISTRY.clear()
    REGISTRY.update(original)