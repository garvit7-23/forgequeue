import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import enqueue
from forgequeue.redis_client import redis_client
from forgequeue.workers.pool import shutdown_pool
from forgequeue.workers.worker import run_worker


def wait_for_running(job_id, timeout=10):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if redis_client.hget(f"job:{job_id}", "status") == "RUNNING":
            return True

        time.sleep(0.1)

    return False


def test_worker_pool_graceful_shutdown():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 3},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    shutdown_event = multiprocessing.Event()
    processes = []

    try:
        for _ in range(4):
            process = multiprocessing.Process(
                target=run_worker,
                args=(shutdown_event,),
            )
            process.start()
            processes.append(process)

        assert wait_for_running(job.id), (
            f"Job never reached RUNNING. "
            f"Status: {redis_client.hget(f'job:{job.id}', 'status')}"
        )

        shutdown_pool(processes, shutdown_event)

        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "SUCCEEDED"

        assert redis_client.zscore(
            "queue:processing",
            job.id,
        ) is None

        for process in processes:
            assert process.exitcode == 0

    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)