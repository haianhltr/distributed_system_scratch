import aiohttp, asyncio, time
from typing import Any, Dict, List
from .settings import settings

class ApiClient:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._token: str | None = None

    async def start(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

    async def close(self):
        if self._session: await self._session.close()

    def _headers(self):
        hdr = {"Content-Type": "application/json"}
        if self._token: hdr["Authorization"] = f"Bearer {self._token}"
        return hdr

    async def register(self, ident, capabilities, resources, constraints, meta) -> Dict[str, Any]:
        url = f"{settings.server_base}/bots/register"
        body = {
            "bot_key": ident["bot_key"],
            "instance_id": ident["instance_id"],
            "version": settings.version,
            "capabilities": capabilities,
            "resources": resources,
            "constraints": constraints,
            "meta": {"hostname": ident["hostname"], "os": ident["os"]} | (meta or {})
        }
        async with self._session.post(url, json=body, headers=self._headers()) as r:
            data = await r.json()
            if r.status in (200,201):
                self._token = data["auth"]["access_token"]
                return data
            raise RuntimeError(f"register failed: {r.status} {data}")

    async def heartbeat(self, bot_id, instance_id, running, metrics) -> Dict[str, Any]:
        url = f"{settings.server_base}/bots/{bot_id}/heartbeat"
        body = {"instance_id": instance_id, "running": running, "metrics": metrics}
        async with self._session.put(url, json=body, headers=self._headers()) as r:
            return await r.json()

    async def claim(self, bot_id, ops: List[str], batch: int) -> List[Dict[str, Any]]:
        url = f"{settings.server_base}/jobs/claim"
        body = {"bot_id": bot_id, "operations": ops, "limit": batch}
        async with self._session.post(url, json=body, headers=self._headers()) as r:
            data = await r.json()
            return data.get("jobs", [])

    async def report(self, job_id, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{settings.server_base}/jobs/{job_id}/{action}"
        async with self._session.post(url, json=payload, headers=self._headers()) as r:
            return await r.json()