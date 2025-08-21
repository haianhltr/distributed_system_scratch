from ..jobs import op
from ..state import Job

@op("subtract")
async def handle(job: Job):
    a = job.payload["a"]; b = job.payload["b"]
    return {"result": a - b}