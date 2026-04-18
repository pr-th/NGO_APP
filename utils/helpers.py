from bson import ObjectId
from datetime import datetime, timezone

def new_id() -> str:
    return str(ObjectId())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def serialize(doc: dict) -> dict:
    """Recursively convert ObjectId → str and datetime → ISO string."""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = serialize(v)
        elif isinstance(v, list):
            out[k] = [serialize(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
        else:
            out[k] = v
    return out
