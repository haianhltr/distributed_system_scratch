from dataclasses import dataclass
import os

def _int(name, default): return int(os.getenv(name, default))
def _str(name, default): return os.getenv(name, default)

@dataclass(frozen=True)
class Settings:
    server_base: str = _str("SERVER_BASE", "http://localhost:8000/v1")
    heartbeat_interval: int = _int("HEARTBEAT_INTERVAL_SEC", 30)
    bot_lease_ttl: int = _int("BOT_LEASE_TTL_SEC", 120)
    job_lease_ttl: int = _int("JOB_LEASE_TTL_SEC", 180)
    claim_batch_size: int = _int("CLAIM_BATCH_SIZE", 5)
    max_concurrency: int = _int("MAX_CONCURRENCY", 2)
    min_backoff_ms: int = _int("MIN_BACKOFF_MS", 500)
    max_backoff_ms: int = _int("MAX_BACKOFF_MS", 60000)
    version: str = _str("BOT_VERSION", "1.0.0")

settings = Settings()