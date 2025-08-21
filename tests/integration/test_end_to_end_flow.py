"""
End-to-End Flow Integration Tests

📚 Documentation: test_end_to_end_flow_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_end_to_end_flow_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains integration tests for the complete system workflow.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from bot.machine import Bot
from bot.api import ApiClient
from bot.scheduler import Scheduler
from bot import outbox

class TestEndToEndFlow:
    @pytest.mark.asyncio
    async def test_register_claim_process_report_flow(self, mock_identity):
        """Test complete flow from registration to job completion."""
        # Setup mock responses
        register_response = {
            "bot_id": "bot_123",
            "auth": {"access_token": "token_xyz"},
            "assignment": {
                "operations": ["sum"],
                "max_concurrency": 2
            }
        }
        
        claim_response = [
            {"id": "job_1", "op": "sum", "payload": {"a": 5, "b": 3}},
            {"id": "job_2", "op": "sum", "payload": {"a": 10, "b": 20}}
        ]
        
        heartbeat_response = {
            "lease_extended_to": "2025-01-01T00:00:00Z"
        }
        
        # Create bot with mocked dependencies
        with patch('bot.machine.load_identity', return_value=mock_identity):
            bot = Bot()
        
        # Mock API client
        bot.api = AsyncMock(spec=ApiClient)
        bot.api.register.return_value = register_response
        bot.api.claim.return_value = claim_response
        bot.api.heartbeat.return_value = heartbeat_response
        bot.api.report.return_value = {"status": "accepted"}
        
        # Load plugins (including sum handler)
        with patch('bot.jobs.REGISTRY', {"sum": AsyncMock(side_effect=[
            {"result": 8}, {"result": 30}
        ])}):
            # Start registration
            await bot.api.start()
            await bot._register()
            
            # Verify registration
            assert bot.bot_id == "bot_123"
            assert bot.scheduler is not None
            
            # Run one scheduler tick
            await bot.scheduler.tick()
            
            # Verify jobs were claimed and processed
            bot.api.claim.assert_called_once()
            assert bot.api.report.call_count == 2
            
            # Check report calls
            report_calls = bot.api.report.call_args_list
            assert report_calls[0][0][0] == "job_1"  # job_id
            assert report_calls[0][0][1] == "complete"  # action
            assert report_calls[0][0][2]["result"] == {"result": 8}
            
            assert report_calls[1][0][0] == "job_2"
            assert report_calls[1][0][1] == "complete"
            assert report_calls[1][0][2]["result"] == {"result": 30}

    @pytest.mark.asyncio
    async def test_network_failure_recovery_flow(self, mock_identity, temp_state_dir):
        """Test recovery from network failures using outbox."""
        # Setup
        with patch('bot.machine.load_identity', return_value=mock_identity):
            bot = Bot()
        
        bot.api = AsyncMock(spec=ApiClient)
        bot.api.register.return_value = {
            "bot_id": "bot_123",
            "auth": {"access_token": "token"},
            "assignment": {"operations": ["sum"], "max_concurrency": 1}
        }
        
        # Simulate job processing with network failure on report
        bot.api.claim.return_value = [
            {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}}
        ]
        bot.api.report.side_effect = Exception("Network timeout")
        
        await bot.api.start()
        await bot._register()
        
        # Mock job handler
        with patch('bot.jobs.run_job', return_value={"result": 3}):
            with patch('bot.outbox.OBX', temp_state_dir / "outbox.jsonl"):
                await bot.scheduler.tick()
        
        # Job should be in outbox
        outbox_items = outbox.drain()
        assert len(outbox_items) == 1
        assert outbox_items[0]["job_id"] == "job_1"
        assert outbox_items[0]["action"] == "complete"
        
        # Simulate network recovery
        bot.api.report.side_effect = None
        bot.api.report.return_value = {"status": "accepted"}
        bot.api.claim.return_value = []  # No new jobs
        
        # Re-add item to outbox for flush test
        with patch('bot.outbox.OBX', temp_state_dir / "outbox.jsonl"):
            outbox.append(outbox_items[0])
            
            # Next tick should flush outbox
            await bot.scheduler.tick()
        
        # Verify outbox was flushed
        bot.api.report.assert_called_with("job_1", "complete", outbox_items[0]["payload"])

    @pytest.mark.asyncio
    async def test_assignment_update_flow(self, mock_identity):
        """Test dynamic assignment updates via heartbeat."""
        with patch('bot.machine.load_identity', return_value=mock_identity):
            bot = Bot()
        
        bot.api = AsyncMock(spec=ApiClient)
        bot.api.register.return_value = {
            "bot_id": "bot_123",
            "auth": {"access_token": "token"},
            "assignment": {"operations": ["sum"], "max_concurrency": 1}
        }
        
        await bot.api.start()
        await bot._register()
        
        # Initial state
        assert bot.scheduler.ops == ["sum"]
        old_sem = bot.scheduler.sem
        
        # Simulate assignment update via heartbeat
        bot.api.heartbeat.return_value = {
            "lease_extended_to": "2025-01-01T00:00:00Z",
            "assignment": {
                "operations": ["sum", "multiply", "divide"],
                "max_concurrency": 5
            }
        }
        
        # Manually trigger heartbeat update
        await bot._heartbeat_loop.__wrapped__(bot)  # One iteration
        
        # Verify updates
        assert bot.assignment["operations"] == ["sum", "multiply", "divide"]
        assert bot.assignment["max_concurrency"] == 5
        assert bot.scheduler.ops == ["sum", "multiply", "divide"]
        assert bot.scheduler.sem != old_sem  # New semaphore created

    @pytest.mark.asyncio
    async def test_concurrent_job_processing(self, mock_identity):
        """Test multiple jobs processed concurrently."""
        with patch('bot.machine.load_identity', return_value=mock_identity):
            bot = Bot()
        
        bot.api = AsyncMock(spec=ApiClient)
        bot.api.register.return_value = {
            "bot_id": "bot_123",
            "auth": {"access_token": "token"},
            "assignment": {"operations": ["sum"], "max_concurrency": 3}
        }
        
        # Create jobs that take time to process
        jobs = [
            {"id": f"job_{i}", "op": "sum", "payload": {"a": i, "b": i}}
            for i in range(5)
        ]
        bot.api.claim.return_value = jobs
        bot.api.report.return_value = {"status": "accepted"}
        
        await bot.api.start()
        await bot._register()
        
        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        
        async def slow_handler(job):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return {"result": job.payload["a"] + job.payload["b"]}
        
        with patch('bot.jobs.run_job', side_effect=slow_handler):
            await bot.scheduler.tick()
        
        # Should have processed all jobs
        assert bot.api.report.call_count == 5
        # Should have respected concurrency limit
        assert max_concurrent <= 3