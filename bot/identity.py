import json, os, uuid, hashlib, socket, platform, pathlib
IDENTITY_PATH = pathlib.Path(".state/identity.json")

def _machine_fingerprint():
    host = socket.gethostname()
    sys = platform.platform()
    return hashlib.sha256(f"{host}|{sys}".encode()).hexdigest()

def load_identity():
    IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if IDENTITY_PATH.exists():
        return json.loads(IDENTITY_PATH.read_text())
    ident = {
        "bot_key": _machine_fingerprint(),
        "instance_id": str(uuid.uuid4()),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
    }
    IDENTITY_PATH.write_text(json.dumps(ident, indent=2))
    return ident

def rotate_instance_id():
    ident = load_identity()
    ident["instance_id"] = str(uuid.uuid4())
    IDENTITY_PATH.write_text(json.dumps(ident, indent=2))
    return ident