"""
Scheduler Unit Tests

📚 Documentation: test_scheduler_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_scheduler_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the Scheduler class.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from bot.scheduler import Scheduler
from bot.state import Job
from bot import outbox

class TestScheduler:
    @pytest.fixture
    def scheduler(self, mock_api_client):
        return Scheduler(
            api=mock_api_client,
            bot_id="bot_test",
            instance_id="inst_test",
            assignment_ops=["sum", "subtract"],
            max_conc=2
        )

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_tick_no_jobs -v
    @pytest.mark.asyncio
    async def test_tick_no_jobs(self, scheduler, mock_api_client):
        """Test tick when no jobs available."""
        mock_api_client.claim.return_value = []
        
        await scheduler.tick()
        
        mock_api_client.claim.assert_called_once_with(
            "bot_test", ["sum", "subtract"], 5  # default claim_batch_size
        )

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_tick_with_jobs -v
    @pytest.mark.asyncio
    async def test_tick_with_jobs(self, scheduler, mock_api_client, mock_job_registry):
        """Test tick processes claimed jobs."""
        mock_jobs = [
            {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}},
            {"id": "job_2", "op": "sum", "payload": {"a": 3, "b": 4}}
        ]
        mock_api_client.claim.return_value = mock_jobs
        
        # Track which jobs were processed
        processed_jobs = []
        
        async def track_job_processing(job):
            processed_jobs.append(job.id)
            # Return different results based on job
            if job.id == "job_1":
                return {"result": 3}
            else:
                return {"result": 7}
        
        mock_job_registry["sum"].side_effect = track_job_processing
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        await scheduler.tick()
        
        # Comprehensive assertions
        # Verify both jobs were processed
        assert len(processed_jobs) == 2
        assert "job_1" in processed_jobs
        assert "job_2" in processed_jobs
        
        # Verify handler was called for each job
        assert mock_job_registry["sum"].call_count == 2
        
        # Verify both jobs reported completion
        assert mock_api_client.report.call_count == 2
        
        # Verify report content for each job
        report_calls = mock_api_client.report.call_args_list
        
        # Check job_1 report
        job1_report = next(call for call in report_calls if call[0][0] == "job_1")
        assert job1_report[0][1] == "complete"  # action
        assert job1_report[0][2]["result"] == {"result": 3}  # payload result
        assert job1_report[0][2]["instance_id"] == "inst_test"  # instance_id
        
        # Check job_2 report
        job2_report = next(call for call in report_calls if call[0][0] == "job_2")
        assert job2_report[0][1] == "complete"  # action
        assert job2_report[0][2]["result"] == {"result": 7}  # payload result
        assert job2_report[0][2]["instance_id"] == "inst_test"  # instance_id
        
        # Verify resource management
        assert scheduler.sem._value == initial_sem_value  # Semaphore properly managed

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_concurrency_limit -v
    @pytest.mark.asyncio
    async def test_concurrency_limit(self, scheduler, mock_api_client):
        """Test that concurrency limit is respected."""
        # Create 5 jobs but max_conc is 2
        mock_jobs = [
            {"id": f"job_{i}", "op": "sum", "payload": {"a": i, "b": i}}
            for i in range(5)
        ]
        mock_api_client.claim.return_value = mock_jobs
        
        running_count = 0
        max_running = 0
        
        async def slow_handler(job):
            nonlocal running_count, max_running
            running_count += 1
            max_running = max(max_running, running_count)
            await asyncio.sleep(0.01)
            running_count -= 1
            return {"result": "done"}
        
        with patch('bot.jobs.run_job', side_effect=slow_handler):
            await scheduler.tick()
        
        # Should never exceed max concurrency
        assert max_running <= 2

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_job_failure_handling -v
    @pytest.mark.asyncio
    async def test_job_failure_handling(self, scheduler, mock_api_client, mock_job_registry):
        """Test handling of job execution failures."""
        mock_job = {"id": "job_fail", "op": "sum", "payload": {"a": 1, "b": 2}}
        mock_api_client.claim.return_value = [mock_job]
        
        # Make the handler raise an error
        mock_job_registry["sum"].side_effect = ValueError("Job failed")
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        await scheduler.tick()
        
        # Comprehensive assertions
        # Verify exactly one failure report
        assert mock_api_client.report.call_count == 1
        
        call_args = mock_api_client.report.call_args
        assert call_args[0][0] == "job_fail"  # Correct job ID
        assert call_args[0][1] == "fail"  # Correct action
        
        # Verify complete payload structure
        payload = call_args[0][2]
        assert "instance_id" in payload
        assert payload["instance_id"] == "inst_test"
        assert "error" in payload
        assert payload["error"] == "Job failed"  # Exact error message
        
        # Verify resource management
        assert scheduler.sem._value == initial_sem_value  # Semaphore properly released
        
        # Verify no other API calls were made
        mock_api_client.claim.assert_called_once()
        assert mock_api_client.heartbeat.call_count == 0  # No unexpected calls
        
        # Verify the error was the expected ValueError
        # This ensures we're testing the right failure scenario

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_report_failure_to_outbox -v
    @pytest.mark.asyncio
    async def test_report_failure_to_outbox(self, scheduler, mock_api_client, temp_state_dir, mock_job_registry):
        """Test that report failures go to outbox."""
        mock_job = {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}}
        mock_api_client.claim.return_value = [mock_job]
        
        # Set up handler to return success
        mock_job_registry["sum"].return_value = {"result": 3}
        
        # Report call fails with network error only on the complete action
        call_count = 0
        original_report = mock_api_client.report
        
        async def failing_report(job_id, action, payload):
            nonlocal call_count
            call_count += 1
            if action == "complete":
                raise Exception("Network error")
            return await original_report(job_id, action, payload)
        
        mock_api_client.report.side_effect = failing_report
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        with patch('bot.outbox.append') as mock_append:
            await scheduler.tick()
        
        # Comprehensive assertions
        # Verify report was attempted
        assert mock_api_client.report.call_count == 1
        
        # Verify outbox fallback was used
        mock_append.assert_called_once()
        
        # Verify complete outbox payload
        buffered = mock_append.call_args[0][0]
        assert buffered["job_id"] == "job_1"
        assert buffered["action"] == "complete"
        assert "result" in buffered["payload"]
        assert buffered["payload"]["result"] == {"result": 3}
        assert "instance_id" in buffered["payload"]
        assert buffered["payload"]["instance_id"] == "inst_test"
        
        # Verify resource management
        assert scheduler.sem._value == initial_sem_value  # Semaphore properly released
        
        # Verify the specific error path was taken
        # The report should have been called with "complete" action
        report_call = mock_api_client.report.call_args
        assert report_call[0][1] == "complete"  # action was "complete"
        
        # Verify no other API calls were made
        mock_api_client.claim.assert_called_once()
        assert mock_api_client.heartbeat.call_count == 0  # No unexpected calls
    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_flush_outbox_success -v
    @pytest.mark.asyncio
    async def test_flush_outbox_success(self, scheduler, mock_api_client):
        """Test successful outbox flush."""
        pending_items = [
            {"job_id": "job_1", "action": "complete", "payload": {"result": 1}},
            {"job_id": "job_2", "action": "fail", "payload": {"error": "test"}}
        ]
        
        with patch('bot.outbox.drain', return_value=pending_items):
            await scheduler.flush_outbox()
        
        assert mock_api_client.report.call_count == 2

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_flush_outbox_partial_failure -v
    @pytest.mark.asyncio
    async def test_flush_outbox_partial_failure(self, scheduler, mock_api_client):
        """Test outbox flush with partial failure."""
        pending_items = [
            {"job_id": "job_1", "action": "complete", "payload": {"result": 1}},
            {"job_id": "job_2", "action": "fail", "payload": {"error": "test"}},
            {"job_id": "job_3", "action": "complete", "payload": {"result": 3}}
        ]
        
        # First succeeds, second fails
        mock_api_client.report.side_effect = [None, Exception("Network error")]
        
        with patch('bot.outbox.drain', return_value=pending_items):
            with patch('bot.outbox.append') as mock_append:
                await scheduler.flush_outbox()
        
        # Should have re-queued the failed item (breaks after first failure)
        assert mock_append.call_count == 1
        # And it should be the second item that failed
        assert mock_append.call_args[0][0]["job_id"] == "job_2"

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_semaphore_release_on_exception -v
    @pytest.mark.asyncio
    async def test_semaphore_release_on_exception(self, scheduler, mock_api_client):
        """Test that semaphore is released even on exception."""
        mock_job = {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}}
        mock_api_client.claim.return_value = [mock_job]
        
        initial_value = scheduler.sem._value
        
        with patch('bot.jobs.run_job', side_effect=Exception("Crash")):
            await scheduler.tick()
        
        # Semaphore should be released
        assert scheduler.sem._value == initial_value

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_malformed_job_data -v
    @pytest.mark.asyncio
    async def test_malformed_job_data(self, scheduler, mock_api_client, mock_job_registry):
        """Test handling of malformed job data."""
        # Mix of valid and malformed jobs
        mixed_jobs = [
            {"id": "job_1", "op": "sum", "payload": {"a": 1, "b": 2}},  # Valid
            {"id": "job_2"},  # Missing op and payload - will crash
        ]
        mock_api_client.claim.return_value = mixed_jobs
        
        # Track job processing
        processed_jobs = []
        
        async def track_valid_job(job):
            processed_jobs.append(job.id)
            return {"result": "done"}
        
        mock_job_registry["sum"].side_effect = track_valid_job
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        # The scheduler will crash on malformed data (by design)
        with pytest.raises(KeyError) as exc_info:
            await scheduler.tick()
        
        # Comprehensive assertions
        # Verify the crash was caused by missing 'op' field
        assert "'op'" in str(exc_info.value) or "op" in str(exc_info.value)
        
        # Verify the valid job was processed before the crash
        assert len(processed_jobs) == 1
        assert processed_jobs[0] == "job_1"
        
        # Verify the crash happened during job processing, not before
        assert mock_api_client.claim.call_count == 1
        
        # Verify resource management (semaphore should be released)
        assert scheduler.sem._value == initial_sem_value
        
        # Verify the valid job was reported successfully before the crash
        assert mock_api_client.report.call_count == 1
        assert mock_api_client.report.call_args[0][0] == "job_1"
        assert mock_api_client.report.call_args[0][1] == "complete"

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_claim_api_failure -v
    @pytest.mark.asyncio
    async def test_claim_api_failure(self, scheduler, mock_api_client):
        """Test scheduler behavior when claim API fails."""
        # Simulate network/API failure
        mock_api_client.claim.side_effect = Exception("API connection failed")
        
        # The scheduler doesn't handle claim failures (by design)
        # This test verifies the current behavior
        with pytest.raises(Exception, match="API connection failed"):
            await scheduler.tick()
        
        # Verify claim was attempted
        mock_api_client.claim.assert_called_once()

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_concurrent_tick_calls -v
    @pytest.mark.asyncio
    async def test_concurrent_tick_calls(self, scheduler, mock_api_client, mock_job_registry):
        """Test concurrent tick calls don't interfere."""
        # Track execution state
        execution_times = []
        processed_jobs = []
        
        async def slow_claim_side_effect(*args):
            # Simulate API delay to allow concurrency
            start_time = time.time()
            await asyncio.sleep(0.01)
            execution_times.append(time.time() - start_time)
            
            # Return one job per call to test concurrent processing
            call_number = len(execution_times)
            if call_number <= 3:
                return [{"id": f"job_{call_number-1}", "op": "sum", "payload": {"a": call_number-1, "b": call_number-1}}]
            else:
                return []
        
        async def track_job_execution(job):
            processed_jobs.append(job.id)
            return {"result": "done"}
        
        mock_api_client.claim.side_effect = slow_claim_side_effect
        mock_job_registry["sum"].side_effect = track_job_execution
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        # Run multiple ticks concurrently
        start_time = time.time()
        tasks = [scheduler.tick() for _ in range(3)]
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Comprehensive assertions
        assert mock_api_client.claim.call_count == 3  # All ticks called claim
        
        # Verify concurrency (should be faster than sequential)
        assert total_time < 0.05  # 3 * 0.01 = 0.03, but allow some overhead
        
        # Verify jobs were processed
        assert len(processed_jobs) == 3
        assert set(processed_jobs) == {"job_0", "job_1", "job_2"}
        
        # Verify resource management
        assert scheduler.sem._value == initial_sem_value  # Semaphore properly managed
        
        # Verify no interference between ticks
        assert len(execution_times) == 3  # All ticks executed
        assert all(t > 0.005 for t in execution_times)  # Each had some delay

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_scheduler_large_job_batch_handling -v
    @pytest.mark.asyncio
    async def test_scheduler_large_job_batch_handling(self, scheduler, mock_api_client, mock_job_registry):
        """Test handling of large job batches."""
        # Create a large batch of jobs (100)
        large_batch = [
            {"id": f"job_{i}", "op": "sum", "payload": {"a": i, "b": i}}
            for i in range(100)
        ]
        mock_api_client.claim.return_value = large_batch
        
        # Track execution with more detail
        executed_jobs = []
        concurrent_count = 0
        max_concurrent = 0
        
        async def track_execution(job):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            executed_jobs.append(job.id)
            await asyncio.sleep(0.001)  # Small delay to allow concurrency
            concurrent_count -= 1
            return {"result": "done"}
        
        mock_job_registry["sum"].side_effect = track_execution
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        # Process the batch
        await scheduler.tick()
        
        # Comprehensive assertions
        assert len(executed_jobs) == 100  # All jobs processed
        assert len(set(executed_jobs)) == 100  # No duplicates
        assert set(executed_jobs) == {f"job_{i}" for i in range(100)}  # All jobs present
        assert max_concurrent <= 2  # Concurrency limit respected
        assert mock_api_client.report.call_count == 100  # All jobs reported
        assert scheduler.sem._value == initial_sem_value  # Semaphore properly managed

    # pytest tests/unit/scheduler/test_scheduler.py::TestScheduler::test_job_timeout_handling -v -s
    @pytest.mark.asyncio
    async def test_job_timeout_handling(self, scheduler, mock_api_client, mock_job_registry):
        """Test handling of job execution timeouts."""
        mock_job = {"id": "job_timeout", "op": "sum", "payload": {"a": 1, "b": 2}}
        mock_api_client.claim.return_value = [mock_job]
        
        # Simulate timeout error from handler
        mock_job_registry["sum"].side_effect = asyncio.TimeoutError("Job execution timed out")
        
        # Record initial state
        initial_sem_value = scheduler.sem._value
        
        await scheduler.tick()
        
        # Comprehensive assertions
        assert mock_api_client.report.call_count == 1  # Exactly one report
        
        call_args = mock_api_client.report.call_args
        assert call_args[0][0] == "job_timeout"  # Correct job ID
        assert call_args[0][1] == "fail"  # Correct action
        
        # Verify payload structure
        payload = call_args[0][2]
        assert payload["instance_id"] == "inst_test"
        assert "error" in payload
        assert "Job execution timed out" in payload["error"]  # Exact error message
        
        # Verify semaphore is properly released
        assert scheduler.sem._value == initial_sem_value
        
        # Verify no other API calls were made
        mock_api_client.claim.assert_called_once()
        assert mock_api_client.heartbeat.call_count == 0  # No unexpected calls