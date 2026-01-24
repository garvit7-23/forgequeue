import time
import signal
import sys
import traceback   # ✅ add this

from forgequeue.redis_client import redis_client
from forgequeue.core.queue import dequeue, move_to_dead
from forgequeue.core.job import JobStatus
from forgequeue.core.retry import schedule_retry
from forgequeue.core.metrics import incr, record_timing
from forgequeue.tasks.example import print_message, unstable_task

from api.tasks.send_email_task import send_email_task

SHUTDOWN = False

TASK_REGISTRY = {
    "print_message": print_message,
    "unstable_task": unstable_task,
    "SEND_EMAIL": send_email_task,
}

def handle_shutdown(signum, frame):
    global SHUTDOWN
    print("Worker received shutdown signal")
    SHUTDOWN = True

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def run_worker():
    print("Worker started...")

    while not SHUTDOWN:
        item = dequeue()
        if not item:
            time.sleep(1)
            continue

        job_id, job_data = item
        task_name = job_data["task_name"]

        redis_client.hset(f"job:{job_id}", "status", JobStatus.RUNNING.value)

        start_time = time.time()

        try:
            TASK_REGISTRY[task_name](job_data["payload"])

            duration = time.time() - start_time
            record_timing("job_exec_time", duration)
            incr("jobs_processed")

            redis_client.hset(f"job:{job_id}", "status", JobStatus.DONE.value)
            print(f"Job {job_id} completed in {duration:.2f}s")

        except Exception as e:
            incr("jobs_failed")

            # ✅ SHOW REAL ERROR IN RAILWAY LOGS
            print(f"Job {job_id} failed with error: {repr(e)}")
            traceback.print_exc()

            retries = int(job_data["retries"]) + 1
            redis_client.hset(
                f"job:{job_id}",
                mapping={"status": JobStatus.FAILED.value, "retries": retries},
            )

            if retries <= 3:
                incr("jobs_retried")
                schedule_retry(job_id, retries)
                print(f"Retrying job {job_id} ({retries}/3)")
            else:
                incr("jobs_dead")
                move_to_dead(job_id)
                print(f"Moved job {job_id} to dead queue")

    print("Worker shutting down gracefully")
    sys.exit(0)

if __name__ == "__main__":
    run_worker()
