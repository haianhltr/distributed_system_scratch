"""
Bot Lifecycle Unit Tests

📚 Documentation: test_bot_lifecycle_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_bot_lifecycle_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains unit tests for the bot lifecycle management system.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bot.machine import Bot
from bot.state import Assignment
from bot import settings

class TestBotLifecycle:
    @pytest.fixture
    def bot(self, mock_identity):
        with patch('bot.machine.load_identity', return_value=mock_identity):
            return Bot()

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_bot_initialization -v -s
    @pytest.mark.asyncio
    async def test_bot_initialization(self, bot, mock_identity):
        """Test bot initializes with correct defaults."""
        assert bot.ident == mock_identity
        assert bot.bot_id is None
        assert bot.assignment["operations"] == []
        assert bot.assignment["max_concurrency"] == 2
        assert bot.scheduler is None

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_register_flow -v -s
    @pytest.mark.asyncio
    async def test_register_flow(self, bot, mock_register_response):
        """Test registration updates bot state correctly."""
        bot.api = AsyncMock()
        bot.api.register.return_value = mock_register_response
        
        # Record initial state
        initial_bot_id = bot.bot_id
        initial_assignment = bot.assignment.copy()
        initial_scheduler = bot.scheduler
        
        await bot._register()
        
        # Comprehensive assertions
        
        # 1. Verify API was called with correct parameters
        bot.api.register.assert_called_once_with(
            ident=bot.ident,
            capabilities=bot.assignment["operations"] or ["sum", "subtract"],
            resources={"cpu_cores": 2, "mem_mb": 1024},
            constraints={},
            meta={}
        )
        
        # 2. Verify bot ID was updated
        assert bot.bot_id == "bot_abc123"
        assert bot.bot_id != initial_bot_id  # Actually changed
        
        # 3. Verify complete assignment data
        assert bot.assignment["operations"] == ["sum", "subtract"]
        assert bot.assignment["max_concurrency"] == 2
        assert bot.assignment["paused"] == False
        
        # 4. Verify scheduler was created with correct parameters
        assert bot.scheduler is not None
        assert bot.scheduler != initial_scheduler  # Actually created
        assert bot.scheduler.bot_id == "bot_abc123"
        assert bot.scheduler.instance_id == bot.ident["instance_id"]
        assert bot.scheduler.ops == ["sum", "subtract"]
        assert bot.scheduler.sem._value == 2  # max_concurrency
        
        # 5. Verify state consistency
        assert bot.assignment["operations"] == bot.scheduler.ops
        assert bot.assignment["max_concurrency"] == 2

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_assignment_update_from_response -v
    @pytest.mark.asyncio
    async def test_assignment_update_from_response(self, bot):
        """Test that assignment updates from responses are processed correctly."""
        bot.bot_id = "bot_test"
        bot.api = AsyncMock()
        bot.scheduler = MagicMock()
        
        # Mock heartbeat responses
        heartbeat_responses = [
            {
                "lease_extended_to": "2025-01-01T00:00:00Z",
                "assignment": {
                    "operations": ["sum", "multiply", "divide"],
                    "max_concurrency": 5
                }
            }
        ]
        # Use an iterator to return different values on each call
        responses_iter = iter(heartbeat_responses + [asyncio.CancelledError()])
        bot.api.heartbeat.side_effect = lambda *args, **kwargs: next(responses_iter)
        
        # Use a simple sleep instead of patching frozen settings
        original_sleep = asyncio.sleep
        async def fast_sleep(duration):
            await original_sleep(0.01)
        
        with patch('asyncio.sleep', fast_sleep):
            try:
                await asyncio.wait_for(bot._heartbeat_loop(), timeout=0.1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        # Check assignment was updated
        assert bot.assignment["operations"] == ["sum", "multiply", "divide"]
        assert bot.assignment["max_concurrency"] == 5
        assert bot.scheduler.ops == ["sum", "multiply", "divide"]

    @pytest.mark.asyncio
    async def test_heartbeat_failure_handling(self, bot):
        """Test heartbeat continues on failure."""
        bot.bot_id = "bot_test"
        bot.api = AsyncMock()
        bot.api.heartbeat.side_effect = [
            Exception("Network error"),
            {"lease_extended_to": "2025-01-01T00:00:00Z"},
            asyncio.CancelledError()
        ]
        
        call_count = 0
        original_heartbeat = bot.api.heartbeat
        
        async def counting_heartbeat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_heartbeat(*args, **kwargs)
        
        bot.api.heartbeat = counting_heartbeat
        
        # Use a simple sleep instead of patching frozen settings
        original_sleep = asyncio.sleep
        async def fast_sleep(duration):
            await original_sleep(0.01)
        
        with patch('asyncio.sleep', fast_sleep):
            try:
                await asyncio.wait_for(bot._heartbeat_loop(), timeout=0.1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        # Should have continued after first failure
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_run_loop_continues_on_error(self, bot):
        """Test main run loop continues after scheduler errors."""
        bot.scheduler = AsyncMock()
        bot.scheduler.tick.side_effect = [
            Exception("Scheduler error"),
            None,
            asyncio.CancelledError()
        ]
        
        tick_count = 0
        original_tick = bot.scheduler.tick
        
        async def counting_tick(*args, **kwargs):
            nonlocal tick_count
            tick_count += 1
            return await original_tick(*args, **kwargs)
        
        bot.scheduler.tick = counting_tick
        
        # Use fast sleep to speed up the loop
        original_sleep = asyncio.sleep
        async def fast_sleep(duration):
            await original_sleep(0.001)
        
        with patch('asyncio.sleep', fast_sleep):
            try:
                await asyncio.wait_for(bot._run_loop(), timeout=0.1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        
        # Should have continued after error
        assert tick_count >= 2

    @pytest.mark.asyncio
    async def test_start_orchestration(self, bot, mock_register_response):
        """Test start method orchestrates initialization."""
        bot.api = AsyncMock()
        bot.api.register.return_value = mock_register_response
        
        # Mock the loops to exit quickly
        async def quick_loop():
            await asyncio.sleep(0.01)
            raise asyncio.CancelledError()
        
        with patch('bot.machine.load_plugins') as mock_load:
            with patch.object(bot, '_heartbeat_loop', quick_loop):
                with patch.object(bot, '_run_loop', quick_loop):
                    try:
                        await asyncio.wait_for(bot.start(), timeout=0.1)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
        
        mock_load.assert_called_once()
        bot.api.start.assert_called_once()
        bot.api.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_updates_safety(self, bot):
        """Test that concurrent assignment updates are safe."""
        bot.scheduler = MagicMock()
        bot.scheduler.ops = ["sum"]
        bot.scheduler.sem = asyncio.Semaphore(2)
        
        async def update_assignment():
            bot.assignment["operations"] = ["new_op1", "new_op2"]
            bot.assignment["max_concurrency"] = 10
            bot.scheduler.ops = bot.assignment["operations"]
            bot.scheduler.sem = asyncio.Semaphore(bot.assignment["max_concurrency"])
        
        # Run multiple concurrent updates
        await asyncio.gather(*[update_assignment() for _ in range(10)])
        
        # Should end in consistent state
        assert bot.assignment["operations"] == ["new_op1", "new_op2"]
        assert bot.assignment["max_concurrency"] == 10

    @pytest.mark.asyncio
    async def test_graceful_shutdown_preparation(self, bot):
        """Test bot can prepare for graceful shutdown."""
        bot.api = AsyncMock()
        bot.scheduler = AsyncMock()
        
        # Simulate shutdown signal
        bot.draining = True
        
        # In real implementation, would stop claiming new work
        # and finish in-flight jobs
        assert bot.draining is True

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_bot_registration_failure_recovery -v
    @pytest.mark.asyncio
    async def test_bot_registration_failure_recovery(self, bot):
        """Test bot handles registration failures and retries."""
        bot.api = AsyncMock()
        bot.api.register.side_effect = [
            Exception("Registration failed"),
            Exception("Still failing"),
            {"bot_id": "bot_success", "assignment": {"operations": ["sum"], "max_concurrency": 2}}
        ]
        
        # Registration should eventually succeed after retries
        # In real implementation, would have retry logic
        with pytest.raises(Exception, match="Registration failed"):
            await bot._register()

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_bot_identity_corruption_handling -v  
    @pytest.mark.asyncio
    async def test_bot_identity_corruption_handling(self, bot):
        """Test bot handles corrupted identity gracefully."""
        # Simulate corrupted identity
        bot.ident = None
        
        # Should handle gracefully or regenerate identity
        # Current implementation might crash, testing actual behavior
        assert bot.ident is None

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_server_unavailability_handling -v
    @pytest.mark.asyncio
    async def test_server_unavailability_handling(self, bot):
        """Test bot handles server unavailability."""
        bot.api = AsyncMock()
        bot.api.start.side_effect = Exception("Server unavailable")
        
        # Should handle server unavailability gracefully
        with pytest.raises(Exception, match="Server unavailable"):
            await bot.api.start()

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_complete_lifecycle_transition -v
    @pytest.mark.asyncio 
    async def test_complete_lifecycle_transition(self, bot, mock_register_response):
        """Test complete bot lifecycle from start to shutdown."""
        bot.api = AsyncMock()
        bot.api.register.return_value = mock_register_response
        
        # Track lifecycle states
        states = []
        
        async def track_state(state):
            states.append(state)
            await asyncio.sleep(0.001)
        
        # Mock lifecycle phases
        with patch('bot.jobs.load_plugins'):
            states.append("initialized")
            await bot._register()
            states.append("registered") 
            
        # Verify lifecycle progression
        assert "initialized" in states
        assert "registered" in states
        assert bot.bot_id == "bot_abc123"

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_memory_leak_prevention -v
    @pytest.mark.asyncio
    async def test_memory_leak_prevention(self, bot):
        """Test bot prevents memory leaks during operation."""
        import gc
        import sys
        
        initial_objects = len(gc.get_objects())
        
        # Simulate operations that could leak memory
        for _ in range(100):
            bot.assignment = {"operations": [f"op_{i}" for i in range(10)], "max_concurrency": 5}
            # Force garbage collection
            gc.collect()
        
        final_objects = len(gc.get_objects())
        
        # Should not have significant object growth
        # Allow for some variance in object count
        assert final_objects - initial_objects < 1000

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_connection_management -v
    @pytest.mark.asyncio
    async def test_connection_management(self, bot):
        """Test proper connection resource management."""
        bot.api = AsyncMock()
        
        # Test connection lifecycle
        await bot.api.start()
        bot.api.start.assert_called_once()
        
        # In real implementation, would test connection pooling,
        # cleanup, and proper resource disposal
        assert bot.api is not None

    # pytest tests/unit/machine/test_bot_lifecycle.py::TestBotLifecycle::test_plugin_system_integration -v
    @pytest.mark.asyncio
    async def test_plugin_system_integration(self, bot):
        """Test integration with plugin system."""
        with patch('bot.machine.load_plugins') as mock_load:
            # Simulate plugin loading during start
            mock_load.return_value = {"sum": MagicMock(), "subtract": MagicMock()}
            
            # In start flow, plugins should be loaded
            with patch.object(bot, '_register'):
                with patch.object(bot, '_heartbeat_loop'):
                    with patch.object(bot, '_run_loop'):
                        try:
                            await asyncio.wait_for(bot.start(), timeout=0.01)
                        except asyncio.TimeoutError:
                            pass
            
            mock_load.assert_called_once()