import json, pathlib, time
from typing import Dict, Any, List

OBX = pathlib.Path(".state/outbox.jsonl")

def append(item: Dict[str, Any]):
    OBX.parent.mkdir(parents=True, exist_ok=True)
    with OBX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item) + "\n")

def drain(max_items=1000) -> List[Dict[str, Any]]:
    if not OBX.exists(): return []
    lines = OBX.read_text().splitlines()
    OBX.unlink(missing_ok=True)
    items = [json.loads(l) for l in lines]
    return items[:max_items]