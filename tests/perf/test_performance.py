"""
Performance Tests

📚 Documentation: test_performance_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_performance_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains performance and load testing for the distributed system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from bot.scheduler import Scheduler
from bot.api import ApiClient
from bot import outbox

class TestPerformance:
    @pytest.mark.asyncio
    async def test_claim_throughput(self):
        """Test job claiming throughput."""
        api = AsyncMock(spec=ApiClient)
        scheduler = Scheduler(
            api=api,
            bot_id="bot_perf",
            instance_id="inst_perf",
            assignment_ops=["sum"],
            max_conc=10
        )
        
        # Generate many jobs
        jobs = [
            {"id": f"job_{i}", "op": "sum", "payload": {"a": i, "b": i}}
            for i in range(100)
        ]
        
        api.claim.return_value = jobs[:10]  # Return 10 at a time
        api.report.return_value = {"status": "accepted"}
        
        # Mock fast job handler
        with patch('bot.jobs.run_job', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"result": 0}
            
            start_time = time.time()
            
            # Process 10 ticks (100 jobs total)
            for _ in range(10):
                await scheduler.tick()
            
            elapsed = time.time() - start_time
        
        # Should process 100 jobs quickly
        assert mock_run.call_count == 100
        assert elapsed < 2.0  # Should complete in under 2 seconds
        
        # Calculate throughput
        throughput = 100 / elapsed
        print(f"Job throughput: {throughput:.1f} jobs/second")
        assert throughput > 50  # At least 50 jobs/second

    @pytest.mark.asyncio
    async def test_concurrent_processing_performance(self):
        """Test performance with concurrent job processing."""
        api = AsyncMock(spec=ApiClient)
        scheduler = Scheduler(
            api=api,
            bot_id="bot_perf",
            instance_id="inst_perf",
            assignment_ops=["sum"],
            max_conc=20  # High concurrency
        )
        
        # Generate jobs
        jobs = [
            {"id": f"job_{i}", "op": "sum", "payload": {"a": i, "b": i}}
            for i in range(50)
        ]
        
        api.claim.return_value = jobs
        api.report.return_value = {"status": "accepted"}
        
        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0
        
        async def simulated_work(job):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.1)  # Simulate 100ms of work
            concurrent_count -= 1
            return {"result": "done"}
        
        with patch('bot.jobs.run_job', side_effect=simulated_work):
            start_time = time.time()
            await scheduler.tick()
            elapsed = time.time() - start_time
        
        # With 20 concurrency and 100ms per job, 50 jobs should take ~250ms
        assert elapsed < 0.5  # Should complete in under 500ms
        assert max_concurrent >= 15  # Should use most of available concurrency
        
        print(f"Processed 50 jobs in {elapsed:.2f}s with max concurrency {max_concurrent}")

    @pytest.mark.asyncio
    async def test_outbox_performance(self, temp_state_dir):
        """Test outbox performance with many items."""
        test_file = temp_state_dir / "outbox.jsonl"
        
        with patch('bot.outbox.OBX', test_file):
            # Write many items
            start_time = time.time()
            for i in range(1000):
                outbox.append({
                    "job_id": f"job_{i}",
                    "action": "complete",
                    "payload": {"result": i}
                })
            write_time = time.time() - start_time
            
            # Read all items
            start_time = time.time()
            items = outbox.drain()
            read_time = time.time() - start_time
        
        assert len(items) == 1000
        assert write_time < 0.5  # Should write 1000 items in under 500ms
        assert read_time < 0.1   # Should read 1000 items in under 100ms
        
        print(f"Outbox: wrote 1000 items in {write_time:.3f}s, read in {read_time:.3f}s")

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self):
        """Test that memory usage remains stable during long runs."""
        api = AsyncMock(spec=ApiClient)
        scheduler = Scheduler(
            api=api,
            bot_id="bot_mem",
            instance_id="inst_mem",
            assignment_ops=["sum"],
            max_conc=5
        )
        
        api.report.return_value = {"status": "accepted"}
        
        # Track memory allocations
        import gc
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Process many batches
        for batch in range(10):
            jobs = [
                {"id": f"job_{batch}_{i}", "op": "sum", "payload": {"a": i, "b": i}}
                for i in range(20)
            ]
            api.claim.return_value = jobs
            
            with patch('bot.jobs.run_job', return_value={"result": 0}):
                await scheduler.tick()
            
            # Force garbage collection
            gc.collect()
        
        # Check object count didn't grow significantly
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects
        
        print(f"Object count growth: {object_growth} objects")
        assert object_growth < 1000  # Should not leak many objects

    @pytest.mark.asyncio
    async def test_api_client_connection_pooling(self):
        """Test that API client reuses connections efficiently."""
        from aiohttp import ClientSession, TCPConnector
        
        # Create connector with connection limit
        connector = TCPConnector(limit=5)
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock(spec=ClientSession)
            mock_session_class.return_value = mock_session
            
            client = ApiClient()
            await client.start()
            
            # Simulate many requests
            responses = []
            for i in range(100):
                resp = AsyncMock()
                resp.status = 200
                resp.json = AsyncMock(return_value={"result": i})
                responses.append(resp)
            
            mock_session.post.return_value.__aenter__.side_effect = responses
            
            # Make many concurrent requests
            start_time = time.time()
            tasks = []
            for i in range(100):
                task = client.claim("bot_test", ["sum"], 5)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            
            await client.close()
        
        assert len(results) == 100
        assert elapsed < 1.0  # Should complete quickly with connection pooling
        
        print(f"Made 100 API calls in {elapsed:.2f}s")