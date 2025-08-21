"""
API Client Unit Tests

📚 Documentation: test_api_client_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_api_client_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the API client system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock
from bot.api import ApiClient
from bot.settings import settings

def create_async_context_manager(return_value):
    """Helper to create proper async context manager mock."""
    async_cm = AsyncMock()
    async_cm.__aenter__.return_value = return_value
    async_cm.__aexit__.return_value = None
    return async_cm

class TestApiClient:
    @pytest.mark.asyncio
    async def test_client_lifecycle(self):
        """Test client start/close lifecycle."""
        client = ApiClient()
        assert client._session is None
        
        await client.start()
        assert isinstance(client._session, aiohttp.ClientSession)
        
        await client.close()

    def test_headers_without_token(self):
        """Test headers when no token is set."""
        client = ApiClient()
        headers = client._headers()
        assert headers == {"Content-Type": "application/json"}

    def test_headers_with_token(self):
        """Test headers when token is set."""
        client = ApiClient()
        client._token = "test-token-123"
        headers = client._headers()
        assert headers == {
            "Content-Type": "application/json",
            "Authorization": "Bearer test-token-123"
        }

    @pytest.mark.asyncio
    async def test_register_success(self, mock_identity, mock_session):
        """Test successful bot registration."""
        client = ApiClient()
        client._session = mock_session
        
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {
            "bot_id": "bot_123",
            "auth": {"access_token": "new-token"},
            "assignment": {"operations": ["sum"], "max_concurrency": 2}
        }
        mock_session.post.return_value = create_async_context_manager(mock_response)
        
        result = await client.register(
            ident=mock_identity,
            capabilities=["sum"],
            resources={"cpu_cores": 2},
            constraints={},
            meta={}
        )
        
        assert result["bot_id"] == "bot_123"
        assert client._token == "new-token"
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0].endswith("/bots/register")
        assert call_args[1]["json"]["bot_key"] == mock_identity["bot_key"]

    @pytest.mark.asyncio
    async def test_register_failure(self, mock_identity, mock_session):
        """Test registration failure handling."""
        client = ApiClient()
        client._session = mock_session
        
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json.return_value = {"error": "invalid_version"}
        mock_session.post.return_value = create_async_context_manager(mock_response)
        
        with pytest.raises(RuntimeError, match="register failed: 400"):
            await client.register(
                ident=mock_identity,
                capabilities=["sum"],
                resources={},
                constraints={},
                meta={}
            )

    @pytest.mark.asyncio
    async def test_heartbeat(self, mock_session):
        """Test heartbeat request."""
        client = ApiClient()
        client._session = mock_session
        client._token = "test-token"
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "lease_extended_to": "2025-01-01T00:00:00Z",
            "assignment": {"operations": ["sum", "multiply"]}
        }
        mock_session.put.return_value = create_async_context_manager(mock_response)
        
        result = await client.heartbeat(
            bot_id="bot_123",
            instance_id="inst_123",
            running=[],
            metrics={"cpu": 0.5}
        )
        
        assert "lease_extended_to" in result
        mock_session.put.assert_called_once()
        call_args = mock_session.put.call_args
        assert call_args[0][0].endswith("/bots/bot_123/heartbeat")
        assert call_args[1]["json"]["instance_id"] == "inst_123"

    @pytest.mark.asyncio
    async def test_claim_jobs(self, mock_session):
        """Test claiming jobs."""
        client = ApiClient()
        client._session = mock_session
        client._token = "test-token"
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "jobs": [
                {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}},
                {"id": "job_2", "op": "sum", "payload": {"a": 3, "b": 4}}
            ]
        }
        mock_session.post.return_value = create_async_context_manager(mock_response)
        
        jobs = await client.claim(
            bot_id="bot_123",
            ops=["sum"],
            batch=5
        )
        
        assert len(jobs) == 2
        assert jobs[0]["id"] == "job_1"
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[1]["json"]["limit"] == 5

    @pytest.mark.asyncio
    async def test_report_complete(self, mock_session):
        """Test reporting job completion."""
        client = ApiClient()
        client._session = mock_session
        client._token = "test-token"
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {"status": "accepted"}
        mock_session.post.return_value = create_async_context_manager(mock_response)
        
        result = await client.report(
            job_id="job_123",
            action="complete",
            payload={"result": 8, "instance_id": "inst_123"}
        )
        
        assert result["status"] == "accepted"
        call_args = mock_session.post.call_args
        assert call_args[0][0].endswith("/jobs/job_123/complete")

    @pytest.mark.asyncio
    async def test_session_timeout(self):
        """Test that session is created with proper timeout."""
        client = ApiClient()
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            await client.start()
            
        mock_session_class.assert_called_once()
        timeout_arg = mock_session_class.call_args[1]['timeout']
        assert timeout_arg.total == 30