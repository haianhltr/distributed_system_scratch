from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

class BotState(Enum):
    BOOTSTRAP = auto()
    REGISTER = auto()
    SYNC = auto()
    IDLE = auto()
    CLAIM = auto()
    PROCESS = auto()
    REPORT = auto()
    DEGRADED_NET = auto()
    DRAINING = auto()
    SHUTDOWN = auto()
    BACKOFF = auto()
    QUARANTINED = auto()
    SAFE_HALT = auto()

@dataclass
class Assignment:
    operations: List[str]
    max_concurrency: int
    paused: bool = False

@dataclass
class Job:
    id: str
    op: str
    payload: Dict[str, Any]
    lease_until: Optional[str] = None