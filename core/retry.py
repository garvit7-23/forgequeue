import time
from redis_client import redis_client

RETRY_QUEUE = "queue:retry"
BASE_DELAY = 2  # seconds


def schedule_retry(job_id: str, retries: int):
    delay = BASE_DELAY * (2 ** retries)
    run_at = time.time() + delay

    redis_client.zadd(RETRY_QUEUE, {job_id: run_at})
