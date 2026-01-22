import time
from croniter import croniter
from forgequeue.redis_client import redis_client

CRON_HASH = "queue:cron"
CRON_NEXT = "queue:cron_next"


def run_cron_scheduler():
    print("ðŸ•’ Cron scheduler started...")

    while True:
        now = time.time()
        jobs = redis_client.hgetall(CRON_HASH)

        for job_id, expr in jobs.items():
            next_run = redis_client.zscore(CRON_NEXT, job_id)

            if next_run and next_run > now:
                continue

            # calculate next execution time
            itr = croniter(expr, now)
            next_ts = itr.get_next(float)
            redis_client.zadd(CRON_NEXT, {job_id: next_ts})

            # fetch job metadata ONLY to know priority
            job_data = redis_client.hgetall(f"job:{job_id}")
            if not job_data:
                continue

            priority = job_data["priority"]
            queue_name = f"queue:{priority}"

            # enqueue job ID only (do NOT rewrite job hash)
            redis_client.lpush(queue_name, job_id)

            print(f"ðŸ” Cron job {job_id} enqueued")

        time.sleep(5)


if __name__ == "__main__":
    run_cron_scheduler()

