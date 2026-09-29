import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.metrics import snapshot
from forgequeue.core.queue import enqueue
from forgequeue.redis_client import redis_client
from forgequeue.workers.worker import run_worker


def run_worker_process(shutdown_event):
    import forgequeue.workers.worker as worker_module

    worker_module.RECOVERY_INTERVAL = 60

    run_worker(shutdown_event)


def wait_for_status(job_id, status, timeout=10):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if redis_client.hget(
            f"job:{job_id}",
            "status",
        ) == status:
            return True

        time.sleep(0.1)

    return False


def test_worker_records_execution_metrics():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "metrics integration test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    shutdown_event = multiprocessing.Event()

    process = multiprocessing.Process(
        target=run_worker_process,
        args=(shutdown_event,),
    )

    process.start()

    try:
        assert wait_for_status(
            job.id,
            "SUCCEEDED",
            timeout=10,
        )

        metrics = snapshot()

        assert int(metrics["jobs_processed"]) == 1
        assert float(metrics["job_exec_time"]) > 0
        assert int(metrics["job_exec_time_count"]) == 1

    finally:
        shutdown_event.set()
        process.join(timeout=5)

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)