import time
from forgequeue.redis_client import redis_client
from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import enqueue , schedule_job


# ---------- IMMEDIATE JOB ----------
def enqueue_immediate_jobs():
    jobs = [
        Job.create("print_message", {"message": "LOW priority"}, Priority.LOW),
        Job.create("print_message", {"message": "HIGH priority"}, Priority.HIGH),
        Job.create("print_message", {"message": "NORMAL priority"}, Priority.NORMAL),
    ]

    for job in jobs:
        enqueue(job)
        print(f"ðŸ“¤ Enqueued immediate {job.priority.value} job {job.id}")


# ---------- DELAYED JOB ----------
def enqueue_delayed_job(delay_seconds: int = 10):
    job = Job.create(
        task_name="print_message",
        payload={"message": "Hello from the future"},
        priority=Priority.HIGH
    )



    run_at = time.time() + delay_seconds
    schedule_job(job, run_at)

    print(f"â³ Scheduled job {job.id} to run in {delay_seconds}s")


# ---------- CRON JOB ----------
def register_cron_job():
    job = Job.create(
        task_name="print_message",
        payload={"message": "Hello from cron"},
        priority=Priority.NORMAL
    )

    # IMPORTANT: stable ID for cron jobs
    job.id = "cron-job-1"
    

    # store job metadata ONCE
    redis_client.hset(
        f"job:{job.id}",
        mapping=job.to_dict()
    )

    # register cron schedule (every minute)
    redis_client.hset(
        "queue:cron",
        job.id,
        "* * * * *"
    )

    print("ðŸ•’ Cron job registered: cron-job-1 (every minute)")


# ---------- ENTRY POINT ----------
if __name__ == "__main__":
    print("ðŸš€ ForgeQueue Phase 4 Main")

    enqueue_immediate_jobs()
    enqueue_delayed_job(delay_seconds=10)
    register_cron_job()
