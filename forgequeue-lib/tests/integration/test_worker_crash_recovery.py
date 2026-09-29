import subprocess
import sys
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import enqueue
from forgequeue.redis_client import redis_client


LEASE_DURATION = 30
WORKER_START_TIMEOUT = 10
RECOVERY_TIMEOUT = LEASE_DURATION + 10


def wait_for_running(job_id, timeout=WORKER_START_TIMEOUT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        status = redis_client.hget(f"job:{job_id}", "status")

        if status == "RUNNING":
            return True

        time.sleep(0.1)

    return False


def wait_for_status(job_id, expected_status, timeout):
    deadline = time.time() + timeout

    while time.time() < deadline:
        status = redis_client.hget(f"job:{job_id}", "status")

        if status == expected_status:
            return True

        time.sleep(0.1)

    return False


def test_worker_crash_recovery():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 1},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    worker = None
    recovery_worker = None

    try:
        # Start first worker.
        worker = subprocess.Popen(
            [sys.executable, "-m", "forgequeue.workers.worker"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Wait until it has claimed the job.
        assert wait_for_running(job.id)

        # Kill worker abruptly.
        worker.kill()
        worker.wait(timeout=5)

        # Job should still be RUNNING immediately after crash.
        assert redis_client.hget(f"job:{job.id}", "status") == "RUNNING"

        processing_lease = redis_client.zscore(
            "queue:processing",
            job.id,
        )

        assert processing_lease is not None
        assert processing_lease > time.time()

        # Wait for the lease to expire.
        time.sleep(LEASE_DURATION + 1)

        # Start replacement worker.
        recovery_worker = subprocess.Popen(
            [sys.executable, "-m", "forgequeue.workers.worker"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Replacement worker should recover and execute the job.
        assert wait_for_status(
            job.id,
            "SUCCEEDED",
            timeout=RECOVERY_TIMEOUT,
        )

        assert redis_client.zscore(
            "queue:processing",
            job.id,
        ) is None

        assert redis_client.lrange(
            "queue:default",
            0,
            -1,
        ) == []

    finally:
        if worker is not None and worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)

        if recovery_worker is not None and recovery_worker.poll() is None:
            recovery_worker.kill()
            recovery_worker.wait(timeout=5)