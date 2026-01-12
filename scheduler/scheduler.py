import time
from redis_client import redis_client

SCHEDULED_SET = "queue:scheduled"


def run_scheduler():
    print("⏰ Scheduler started (delayed jobs)...")

    while True:
        now = time.time()

        # fetch one due job at a time
        due = redis_client.zrangebyscore(
            SCHEDULED_SET, 0, now, start=0, num=1
        )

        if not due:
            time.sleep(1)
            continue

        job_id = due[0]
        redis_client.zrem(SCHEDULED_SET, job_id)

        # fetch job metadata ONLY to determine priority
        job_data = redis_client.hgetall(f"job:{job_id}")
        if not job_data:
            continue

        priority = job_data["priority"]
        queue_name = f"queue:{priority}"

        # enqueue job ID only (do NOT touch job hash)
        redis_client.lpush(queue_name, job_id)

        print(f"⏳ Scheduled job {job_id} enqueued")


if __name__ == "__main__":
    run_scheduler()
