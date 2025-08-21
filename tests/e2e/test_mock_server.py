"""
Mock Server End-to-End Tests

📚 Documentation: test_mock_server_writeup.md (same folder)
📋 What to do: Read the writeup file for test analysis and missing coverage

⚠️  MAINTENANCE NOTE: When you modify this test file, ALWAYS update the corresponding 
test_mock_server_writeup.md file to keep them in sync. Both files must reflect the same 
test coverage and analysis.

This file contains end-to-end tests using a mock server.
For comprehensive analysis and missing test coverage, see the documentation above.
"""

import pytest
import asyncio
import aiohttp
from aiohttp import web
import json
from unittest.mock import patch
from bot.machine import Bot

class MockServer:
    """Minimal mock server for e2e testing."""
    
    def __init__(self):
        self.app = web.Application()
        self.setup_routes()
        self.bots = {}
        self.jobs = []
        self.completed_jobs = []
        
    def setup_routes(self):
        self.app.router.add_post('/v1/bots/register', self.register)
        self.app.router.add_put('/v1/bots/{bot_id}/heartbeat', self.heartbeat)
        self.app.router.add_post('/v1/jobs/claim', self.claim)
        self.app.router.add_post('/v1/jobs/{job_id}/complete', self.complete)
        self.app.router.add_post('/v1/jobs/{job_id}/fail', self.fail)
        
    async def register(self, request):
        data = await request.json()
        bot_id = f"bot_{len(self.bots) + 1}"
        self.bots[bot_id] = {
            "instance_id": data["instance_id"],
            "capabilities": data["capabilities"],
            "last_heartbeat": asyncio.get_event_loop().time()
        }
        return web.json_response({
            "bot_id": bot_id,
            "auth": {"access_token": f"token_{bot_id}"},
            "assignment": {
                "operations": data["capabilities"],
                "max_concurrency": 2
            }
        }, status=201)
    
    async def heartbeat(self, request):
        bot_id = request.match_info['bot_id']
        if bot_id in self.bots:
            self.bots[bot_id]["last_heartbeat"] = asyncio.get_event_loop().time()
            return web.json_response({
                "lease_extended_to": "2025-01-01T00:00:00Z"
            })
        return web.json_response({"error": "bot not found"}, status=404)
    
    async def claim(self, request):
        data = await request.json()
        bot_id = data["bot_id"]
        if bot_id not in self.bots:
            return web.json_response({"error": "bot not found"}, status=404)
        
        # Return available jobs
        claimed = []
        for job in self.jobs[:data["limit"]]:
            if job["op"] in data["operations"] and job.get("status") == "pending":
                job["status"] = "claimed"
                job["bot_id"] = bot_id
                claimed.append(job)
        
        return web.json_response({"jobs": claimed})
    
    async def complete(self, request):
        job_id = request.match_info['job_id']
        data = await request.json()
        self.completed_jobs.append({
            "job_id": job_id,
            "status": "completed",
            "result": data.get("result"),
            "instance_id": data.get("instance_id")
        })
        return web.json_response({"status": "accepted"})
    
    async def fail(self, request):
        job_id = request.match_info['job_id']
        data = await request.json()
        self.completed_jobs.append({
            "job_id": job_id,
            "status": "failed",
            "error": data.get("error"),
            "instance_id": data.get("instance_id")
        })
        return web.json_response({"status": "accepted"})
    
    def add_job(self, job_id, op, payload):
        self.jobs.append({
            "id": job_id,
            "op": op,
            "payload": payload,
            "status": "pending"
        })


class TestE2EWithMockServer:
    @pytest.fixture
    async def mock_server(self, aiohttp_client):
        """Create and start mock server."""
        server = MockServer()
        client = await aiohttp_client(server.app)
        server.base_url = str(client.make_url(''))
        return server
    
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_server):
        """Test complete happy path with mock server."""
        # Add test jobs
        mock_server.add_job("job_1", "sum", {"a": 5, "b": 3})
        mock_server.add_job("job_2", "sum", {"a": 10, "b": 20})
        
        # Create bot with mock server URL
        with patch('bot.settings.settings.server_base', f"{mock_server.base_url}v1"):
            with patch('bot.machine.load_identity', return_value={
                "bot_key": "test-key",
                "instance_id": "test-instance",
                "hostname": "test-host",
                "os": "test-os"
            }):
                bot = Bot()
                
                # Mock the sum handler
                with patch('bot.jobs.REGISTRY', {"sum": lambda job: 
                    {"result": job.payload["a"] + job.payload["b"]}
                }):
                    # Start bot
                    await bot.api.start()
                    await bot._register()
                    
                    # Verify registration
                    assert bot.bot_id == "bot_1"
                    assert "bot_1" in mock_server.bots
                    
                    # Run one tick
                    await bot.scheduler.tick()
                    
                    # Verify jobs were completed
                    assert len(mock_server.completed_jobs) == 2
                    assert mock_server.completed_jobs[0]["job_id"] == "job_1"
                    assert mock_server.completed_jobs[0]["result"]["result"] == 8
                    assert mock_server.completed_jobs[1]["job_id"] == "job_2"
                    assert mock_server.completed_jobs[1]["result"]["result"] == 30
                    
                await bot.api.close()
    
    @pytest.mark.asyncio
    async def test_network_flap_recovery(self, mock_server, temp_state_dir):
        """Test recovery from network interruption."""
        mock_server.add_job("job_1", "sum", {"a": 1, "b": 2})
        
        with patch('bot.settings.settings.server_base', f"{mock_server.base_url}v1"):
            with patch('bot.machine.load_identity', return_value={
                "bot_key": "test-key",
                "instance_id": "test-instance",
                "hostname": "test-host",
                "os": "test-os"
            }):
                bot = Bot()
                
                # Setup to fail first report attempt
                original_complete = mock_server.complete
                call_count = 0
                
                async def flaky_complete(request):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return web.json_response({"error": "timeout"}, status=503)
                    return await original_complete(request)
                
                mock_server.complete = flaky_complete
                
                with patch('bot.jobs.REGISTRY', {"sum": lambda job: {"result": 3}}):
                    with patch('bot.outbox.OBX', temp_state_dir / "outbox.jsonl"):
                        await bot.api.start()
                        await bot._register()
                        
                        # First tick - job processes but report fails
                        await bot.scheduler.tick()
                        
                        # Should have buffered to outbox
                        assert len(mock_server.completed_jobs) == 0
                        
                        # Second tick - should retry from outbox
                        mock_server.jobs = []  # No new jobs
                        await bot.scheduler.tick()
                        
                        # Should have succeeded on retry
                        assert len(mock_server.completed_jobs) == 1
                        assert mock_server.completed_jobs[0]["result"]["result"] == 3
                
                await bot.api.close()
    
    @pytest.mark.asyncio
    async def test_concurrent_bots(self, mock_server):
        """Test multiple bots working concurrently."""
        # Add many jobs
        for i in range(10):
            mock_server.add_job(f"job_{i}", "sum", {"a": i, "b": i})
        
        async def run_bot(bot_num):
            with patch('bot.settings.settings.server_base', f"{mock_server.base_url}v1"):
                with patch('bot.machine.load_identity', return_value={
                    "bot_key": f"key-{bot_num}",
                    "instance_id": f"instance-{bot_num}",
                    "hostname": "test-host",
                    "os": "test-os"
                }):
                    bot = Bot()
                    with patch('bot.jobs.REGISTRY', {"sum": lambda job: 
                        {"result": job.payload["a"] + job.payload["b"]}
                    }):
                        await bot.api.start()
                        await bot._register()
                        await bot.scheduler.tick()
                    await bot.api.close()
        
        # Run 3 bots concurrently
        await asyncio.gather(*[run_bot(i) for i in range(3)])
        
        # All jobs should be completed
        assert len(mock_server.completed_jobs) == 10
        
        # Jobs should be distributed across bots
        bot_ids = {job["instance_id"] for job in mock_server.completed_jobs}
        assert len(bot_ids) == 3  # All 3 bots processed some jobs