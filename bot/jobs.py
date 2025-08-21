import importlib, pkgutil, asyncio, traceback, time
from typing import Dict, Callable, Any
from .state import Job

Handler = Callable[[Job], "asyncio.Future[Any]"]
REGISTRY: Dict[str, Handler] = {}

def op(name: str):
    def deco(fn: Handler):
        REGISTRY[name] = fn
        return fn
    return deco

def load_plugins():
    import bot.plugins as pkg
    for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(m.name)  # modules register via @op

async def run_job(job: Job):
    if job.op not in REGISTRY:
        raise RuntimeError(f"No handler for op={job.op}")
    handler = REGISTRY[job.op]
    return await handler(job)