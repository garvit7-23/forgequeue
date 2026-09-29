import time
import signal
import sys
import traceback   # ✅ add this
import threading

from forgequeue.redis_client import redis_client

from forgequeue.core.queue import (
    dequeue,
    acknowledge_job,
    resolve_failed_job,
    recover_expired_jobs,
    renew_lease,
)
from forgequeue.core.retry import (
    calculate_retry_delay,
    MAX_RETRIES,
)
from forgequeue.core.metrics import incr, record_timing
import forgequeue.tasks.example 

SHUTDOWN = False
RECOVERY_INTERVAL = 5
HEARTBEAT_INTERVAL = 10

from forgequeue.core.task_registry import get_task

def handle_shutdown(signum, frame):
    global SHUTDOWN
    print("Worker received shutdown signal")
    SHUTDOWN = True

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def renew_lease_periodically(
    job_id,
    execution_token,
    stop_event,
):
    while not stop_event.wait(HEARTBEAT_INTERVAL):
        try:
            renew_lease(job_id, execution_token)
        except ValueError:
            # The execution no longer owns the job.
            return
        except Exception:
            # Redis/network failure should not silently kill
            # the worker's heartbeat thread.
            traceback.print_exc()

def run_worker(shutdown_event=None):
    print("Worker started...")

    last_recovery = 0

    while not SHUTDOWN and not (
        shutdown_event and shutdown_event.is_set()
    ):
        now = time.time()

        if now - last_recovery >= RECOVERY_INTERVAL:
            recovered = recover_expired_jobs()

            if recovered:
                print(
                    f"Recovered {len(recovered)} expired job(s)"
                )

            last_recovery = now

        item = dequeue()
        if not item:
            time.sleep(1)
            continue

        job_id, job_data , execution_token = item
        task_name = job_data["task_name"]

        

        start_time = time.time()

        heartbeat_stop = threading.Event()

        heartbeat_thread = threading.Thread(
            target=renew_lease_periodically,
            args=(
                job_id,
                execution_token,
                heartbeat_stop,
            ),
            daemon=True,
        )

        heartbeat_thread.start()

        try:
            task = get_task(task_name)
            task(job_data["payload"])

            duration = time.time() - start_time
            record_timing("job_exec_time", duration)
            incr("jobs_processed")

            acknowledge_job(
                job_id,
                execution_token,
                            )
            print(f"Job {job_id} completed in {duration:.2f}s")

        except Exception as e:
            incr("jobs_failed")

            # ✅ SHOW REAL ERROR IN RAILWAY LOGS
            print(f"Job {job_id} failed with error: {repr(e)}")
            traceback.print_exc()

            retries = int(job_data["retries"]) + 1

            delay = calculate_retry_delay(retries)
            run_at = time.time() + delay

            result = resolve_failed_job(
                job_id,
                execution_token,
                retries,
                run_at,
                MAX_RETRIES,
              )

            if result == 1:
                incr("jobs_retried")
                print(f"Retrying job {job_id} ({retries}/{MAX_RETRIES})")
            elif result == 2:
                incr("jobs_dead")
                print(f"Moved job {job_id} to dead queue")

    print("Worker shutting down gracefully")
    sys.exit(0)

if __name__ == "__main__":
    run_worker()
