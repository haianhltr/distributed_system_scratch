import asyncio, time
from typing import List
from .settings import settings
from .state import Job
from . import outbox
from .jobs import run_job
from .api import ApiClient

class Scheduler:
    def __init__(self, api: ApiClient, bot_id: str, instance_id: str, assignment_ops: List[str], max_conc: int):
        self.api, self.bot_id, self.instance_id = api, bot_id, instance_id
        self.ops = assignment_ops
        self.sem = asyncio.Semaphore(max_conc)

    # ================================
    # This is the function that processes a single job
    # ================================
    async def _process_one(self, raw):
        job = Job(id=raw["id"], op=raw["op"], payload=raw["payload"], lease_until=raw.get("lease_until"))
        try:
            result = await run_job(job)
        except Exception as e:
            # Job execution failed
            payload = {"instance_id": self.instance_id, "error": str(e)}
            try:
                await self.api.report(job.id, "fail", payload)
            except Exception:
                outbox.append({"job_id": job.id, "action": "fail", "payload": payload})
        else:
            # Job succeeded, try to report success
            payload = {"instance_id": self.instance_id, "result": result}
            try:
                await self.api.report(job.id, "complete", payload)
            except Exception:
                outbox.append({"job_id": job.id, "action": "complete", "payload": payload})

    # ================================
    # This is the function that flushes the outbox
    # ================================
    async def flush_outbox(self):
        for item in outbox.drain():
            try:
                await self.api.report(item["job_id"], item["action"], item["payload"])
            except Exception:
                outbox.append(item)  # put back and bail
                break

    # ================================
    # This is the main function that runs the scheduler
    # ================================  
    async def tick(self):
        # Step 1: Process any failed API calls from previous attempts
        await self.flush_outbox()
        
        # Step 2: Ask the server for available jobs
        # This requests up to claim_batch_size jobs that this bot can handle
        jobs = await self.api.claim(self.bot_id, self.ops, settings.claim_batch_size)
        
        # Step 3: If no jobs available, sleep briefly and exit
        # This prevents hammering the server when there's no work
        if not jobs:
            await asyncio.sleep(0.4)  # small jitter to avoid thundering herd
            return
        
        # Step 4: Process all available jobs concurrently
        tasks = []
        for raw in jobs:
            # Wait for an available concurrency slot before starting this job
            # This ensures we never exceed max_concurrency limit
            await self.sem.acquire()
            
            # Create an async task for this job and add it to our task list
            # The _run_guarded wrapper ensures the semaphore is released
            tasks.append(asyncio.create_task(self._run_guarded(raw)))
        
        # Step 5: Wait for all jobs to complete
        # This blocks until every job finishes (success or failure)
        await asyncio.gather(*tasks)

    # ================================
    # This is a wrapper that ensures the semaphore is released even if the job fails
    # ================================
    async def _run_guarded(self, raw):
        try:
            # Execute the actual job (sum, subtract, etc.)
            await self._process_one(raw)
        finally:
            # Always release the semaphore slot, even if job fails
            # This ensures other jobs can start running
            self.sem.release()