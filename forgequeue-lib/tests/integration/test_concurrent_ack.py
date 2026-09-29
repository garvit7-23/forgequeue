import multiprocessing

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    acknowledge_job,
    dequeue,
    enqueue,
)
from forgequeue.redis_client import redis_client


NUM_JOBS = 50
NUM_WORKERS = 5


def acknowledge_jobs(executions, result_queue):
    results = []

    for job_id, execution_token in executions:
        try:
            acknowledge_job(
                job_id,
                execution_token,
            )
            results.append((job_id, True))
        except Exception:
            results.append((job_id, False))

    result_queue.put(results)


def test_multiple_workers_ack_independent_jobs_concurrently():
    redis_client.flushdb()

    jobs = []

    for i in range(NUM_JOBS):
        job = Job.create(
            task_name="print_message",
            payload={"message": f"ack test {i}"},
            priority=Priority.NORMAL,
        )

        enqueue(job)
        jobs.append(job)

    executions = []

    for _ in range(NUM_JOBS):
        result = dequeue()

        assert result is not None

        job_id, job_data, execution_token = result

        executions.append(
            (
                job_id,
                execution_token,
            )
        )

    assert len(executions) == NUM_JOBS

    # Split executions among worker processes.
    chunks = [
        executions[i::NUM_WORKERS]
        for i in range(NUM_WORKERS)
    ]

    result_queue = multiprocessing.Queue()
    processes = []

    for chunk in chunks:
        process = multiprocessing.Process(
            target=acknowledge_jobs,
            args=(chunk, result_queue),
        )

        process.start()
        processes.append(process)

    for process in processes:
        process.join(timeout=10)
        assert not process.is_alive()

    results = []

    for _ in range(NUM_WORKERS):
        results.extend(
            result_queue.get(timeout=5)
        )

    assert len(results) == NUM_JOBS

    # Every ACK should succeed.
    assert all(
        success
        for _, success in results
    )

    # Every job should be terminal.
    for job in jobs:
        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "SUCCEEDED"

    # No processing leases should remain.
    assert redis_client.zcard(
        "queue:processing"
    ) == 0