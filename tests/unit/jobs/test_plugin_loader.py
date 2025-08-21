"""
Plugin Loader Unit Tests

📚 Documentation: test_plugin_loader_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_plugin_loader_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the plugin system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import sys
from unittest.mock import patch, MagicMock
from bot.jobs import op, load_plugins, run_job, REGISTRY, Handler
from bot.state import Job

class TestPluginSystem:
    def test_op_decorator(self):
        """Test that @op decorator registers handlers."""
        # Clear registry first
        REGISTRY.clear()
        
        @op("test_op")
        async def test_handler(job: Job):
            return {"test": "result"}
        
        assert "test_op" in REGISTRY
        assert REGISTRY["test_op"] == test_handler

    def test_op_decorator_overwrites(self):
        """Test that duplicate ops overwrite previous handlers."""
        REGISTRY.clear()
        
        @op("duplicate")
        async def handler1(job: Job):
            return 1
        
        @op("duplicate")
        async def handler2(job: Job):
            return 2
        
        assert REGISTRY["duplicate"] == handler2

    @patch('pkgutil.iter_modules')
    @patch('importlib.import_module')
    def test_load_plugins(self, mock_import, mock_iter):
        """Test plugin loading mechanism."""
        # Mock finding plugin modules
        mock_module = MagicMock()
        mock_module.name = "bot.plugins.test_plugin"
        mock_iter.return_value = [mock_module]
        
        load_plugins()
        
        mock_import.assert_called_once_with("bot.plugins.test_plugin")

    @pytest.mark.asyncio
    async def test_run_job_success(self):
        """Test running a job with registered handler."""
        REGISTRY.clear()
        
        @op("test_sum")
        async def sum_handler(job: Job):
            return {"result": job.payload["a"] + job.payload["b"]}
        
        job = Job(
            id="job_test",
            op="test_sum",
            payload={"a": 5, "b": 3}
        )
        
        result = await run_job(job)
        assert result == {"result": 8}

    @pytest.mark.asyncio
    async def test_run_job_missing_handler(self):
        """Test running job with no handler raises error."""
        REGISTRY.clear()
        
        job = Job(
            id="job_test",
            op="unknown_op",
            payload={}
        )
        
        with pytest.raises(RuntimeError, match="No handler for op=unknown_op"):
            await run_job(job)

    @pytest.mark.asyncio
    async def test_handler_with_exception(self):
        """Test handler that raises exception."""
        REGISTRY.clear()
        
        @op("failing_op")
        async def failing_handler(job: Job):
            raise ValueError("Handler failed")
        
        job = Job(
            id="job_fail",
            op="failing_op",
            payload={}
        )
        
        with pytest.raises(ValueError, match="Handler failed"):
            await run_job(job)

    @pytest.mark.asyncio
    async def test_handler_with_async_operations(self):
        """Test handler with async operations."""
        REGISTRY.clear()
        import asyncio
        
        @op("async_op")
        async def async_handler(job: Job):
            await asyncio.sleep(0.001)  # Simulate async work
            return {"async": True, "data": job.payload.get("data")}
        
        job = Job(
            id="job_async",
            op="async_op",
            payload={"data": "test"}
        )
        
        result = await run_job(job)
        assert result == {"async": True, "data": "test"}

    def test_handler_type_hint(self):
        """Test that Handler type hint is correct."""
        from typing import get_type_hints
        
        @op("typed_op")
        async def typed_handler(job: Job):
            return {}
        
        # Handler should accept Job and return Future[Any]
        hints = get_type_hints(typed_handler)
        assert hints['job'] == Job