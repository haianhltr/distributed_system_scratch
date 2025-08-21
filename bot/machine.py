import asyncio, time
from .identity import load_identity
from .settings import settings
from .api import ApiClient
from .jobs import load_plugins
from .scheduler import Scheduler

class Bot:
    def __init__(self):
        self.ident = load_identity()
        self.bot_id = None
        self.assignment = {"operations": [], "max_concurrency": settings.max_concurrency}
        self.api = ApiClient()
        self.scheduler: Scheduler | None = None

    async def start(self):
        load_plugins()
        await self.api.start()
        await self._register()
        asyncio.create_task(self._heartbeat_loop())
        await self._run_loop()

    async def _register(self):
        data = await self.api.register(
            ident=self.ident,
            capabilities=self.assignment["operations"] or ["sum", "subtract"],
            resources={"cpu_cores": 2, "mem_mb": 1024},
            constraints={},
            meta={}
        )
        self.bot_id = data["bot_id"]
        self.assignment = data.get("assignment", self.assignment)
        self.scheduler = Scheduler(
            api=self.api,
            bot_id=self.bot_id,
            instance_id=self.ident["instance_id"],
            assignment_ops=self.assignment["operations"],
            max_conc=self.assignment["max_concurrency"],
        )

    async def _heartbeat_loop(self):
        while True:
            try:
                running = []  # you can add current jobs tracking
                metrics = {"cpu": 0.2, "mem_mb": 256}
                resp = await self.api.heartbeat(self.bot_id, self.ident["instance_id"], running, metrics)
                # react to assignment/config deltas
                if "assignment" in resp:
                    self.assignment = resp["assignment"]
                    if self.scheduler:
                        self.scheduler.ops = self.assignment["operations"]
                        self.scheduler.sem = asyncio.Semaphore(self.assignment["max_concurrency"])
            except Exception:
                # on repeated failures you might degrade activity
                pass
            await asyncio.sleep(settings.heartbeat_interval)

    async def _run_loop(self):
        while True:
            try:
                await self.scheduler.tick()
            except Exception:
                await asyncio.sleep(1.0)  # backoff on unexpected error