import os, json, time
from typing import List, Dict, Any

_redis = None
def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _redis = redis.Redis(host=host, port=port, decode_responses=True, socket_connect_timeout=0.25)
        # probe
        _redis.ping()
        return _redis
    except Exception:
        _redis = False
        return None

def set_short_term(session_key: str, messages: List[Dict[str, Any]], ttl_seconds: int = 1800):
    r = _get_redis()
    if not r: 
        return False
    r.setex(f"st:{session_key}", ttl_seconds, json.dumps(messages))
    return True

def get_short_term(session_key: str):
    r = _get_redis()
    if not r:
        return None
    v = r.get(f"st:{session_key}")
    if not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None
