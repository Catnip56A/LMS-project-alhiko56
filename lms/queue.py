"""
Redis-backed job queue (RQ). Connection is lazy (redis-py/RQ don't connect until the
first real operation), so importing this module doesn't require Redis to already be up.
"""
import os
from redis import Redis
from rq import Queue

QUEUE_NAME = 'lms-jobs'


def get_redis_connection():
    return Redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))


# rq defaults to a 180s job timeout, which is far too short for Whisper transcription
# (~5x realtime on CPU, so a 50-minute lecture needs ~10 minutes). A timed-out horse is
# SIGKILLed, so the recurring sweep's finally-block re-enqueue never runs and the sweep
# stops until the worker restarts.
DEFAULT_JOB_TIMEOUT = int(os.environ.get('RQ_JOB_TIMEOUT_SECONDS', 3600))

job_queue = Queue(QUEUE_NAME, connection=get_redis_connection(), default_timeout=DEFAULT_JOB_TIMEOUT)
