import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    enqueue,
    recover_expired_jobs,
)
from forgequeue.redis_client import redis_client
from forgequeue.workers.worker import run_worker


def run_worker_without_recovery(shutdown_event):
    import forgequeue.workers.worker as worker_module

    # Prevent the worker's own recovery loop from reclaiming the
    # deliberately expired lease before the heartbeat gets a chance
    # to renew it.
    worker_module.RECOVERY_INTERVAL = 60

    run_worker(shutdown_event)


def wait_for_running(job_id, timeout=10):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if redis_client.hget(
            f"job:{job_id}",
            "status",
        ) == "RUNNING":
            return True

        time.sleep(0.1)

    return False


def test_worker_renews_lease_during_long_running_task():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 20},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    shutdown_event = multiprocessing.Event()

    process = multiprocessing.Process(
        target=run_worker_without_recovery,
        args=(shutdown_event,),
    )

    process.start()

    try:
        assert wait_for_running(job.id)

        # Deliberately expire the lease while the task is still running.
        redis_client.zadd(
            PROCESSING_QUEUE,
            {job.id: time.time() - 1},
        )

        # HEARTBEAT_INTERVAL is currently 10 seconds.
        # Give the heartbeat enough time to execute.
        time.sleep(11.5)

        # The worker should have renewed its lease.
        lease = redis_client.zscore(
            PROCESSING_QUEUE,
            job.id,
        )

        assert lease is not None
        assert lease > time.time()

        # Therefore recovery must not reclaim the execution.
        recovered = recover_expired_jobs()

        assert recovered == []

        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "RUNNING"

        # Allow the task to finish.
        process.join(timeout=10)

        if process.is_alive():
            process.terminate()
            process.join()

        assert not process.is_alive()

        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "SUCCEEDED"

    finally:
        if process.is_alive():
            shutdown_event.set()
            process.join(timeout=5)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)