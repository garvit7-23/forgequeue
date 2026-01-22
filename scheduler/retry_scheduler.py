import time
from redis_client import redis_client
from core.queue import DEFAULT_QUEUE
from core.retry import schedule_retry
from core.queue import move_to_dead


RETRY_QUEUE = "queue:retry"


def run_retry_scheduler():
    print("⏱️ Retry scheduler started...")
    while True:
        now = time.time()
        ready = redis_client.zrangebyscore(
            RETRY_QUEUE, 0, now, start=0, num=1
        )

        if not ready:
            time.sleep(1)
            continue

        job_id = ready[0]
        redis_client.zrem(RETRY_QUEUE, job_id)
        redis_client.lpush(DEFAULT_QUEUE, job_id)
        print(f"🔁 Retrying job {job_id}")


if __name__ == "__main__":
    run_retry_scheduler()
