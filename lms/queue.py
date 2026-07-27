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


job_queue = Queue(QUEUE_NAME, connection=get_redis_connection())
