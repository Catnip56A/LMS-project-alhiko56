import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Falls back to in-memory storage (per-process, not shared) if Redis isn't configured —
# fine for one-off local scripts, but rate limits won't be consistent across multiple
# app/worker processes without REDIS_URL set (see docker-compose.yml's redis-dev service).
_storage_uri = os.environ.get('REDIS_URL', 'memory://')

limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri, default_limits=[])
