import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    acknowledge_job,
    dequeue,
    enqueue,
    recover_expired_jobs,
)
from forgequeue.redis_client import redis_client
from forgequeue.workers.worker import run_worker


def run_worker_without_recovery(shutdown_event):
    import forgequeue.workers.worker as worker_module

    # We control recovery manually in this test.
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


def test_old_worker_cannot_interfere_after_ownership_loss():
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
        # Worker A must have claimed the job.
        assert wait_for_running(job.id)

        # Force Worker A's lease to expire.
        redis_client.zadd(
            PROCESSING_QUEUE,
            {job.id: time.time() - 1},
        )

        # Recover Worker A's execution.
        recovered = recover_expired_jobs()

        assert job.id in recovered

        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "QUEUED"

        # Worker B claims the recovered job.
        result = dequeue()

        assert result is not None

        worker_b_job_id, worker_b_data, worker_b_token = result

        assert worker_b_job_id == job.id
        assert worker_b_data["status"] == "RUNNING"

        # Worker B now owns the execution.
        assert redis_client.hget(
            f"job:{job.id}",
            "execution_token",
        ) == worker_b_token

        # Give Worker A enough time to finish its 20-second task.
        # Its heartbeat should have already stopped after ownership loss.
        process.join(timeout=15)

        # Worker A may still be alive because it returns to its
        # normal polling loop after the stale ACK/failure path.
        assert process.is_alive()

        # Most importantly, Worker A must not have changed
        # Worker B's execution state.
        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "RUNNING"

        assert redis_client.hget(
            f"job:{job.id}",
            "execution_token",
        ) == worker_b_token

        # Worker B can still acknowledge its own execution.
        acknowledge_job(
            job.id,
            worker_b_token,
        )

        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "SUCCEEDED"

    finally:
        shutdown_event.set()

        process.join(timeout=5)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)