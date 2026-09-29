import multiprocessing

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import dequeue, enqueue
from forgequeue.redis_client import redis_client


NUM_WORKERS = 5
JOBS_PER_WORKER = 10


def claim_jobs(worker_result_queue):
    claimed = []

    for _ in range(JOBS_PER_WORKER):
        result = dequeue()

        if result is None:
            break

        job_id, job_data, execution_token = result

        claimed.append(
            (
                job_id,
                execution_token,
            )
        )

    worker_result_queue.put(claimed)


def test_multiple_workers_claim_each_job_only_once():
    redis_client.flushdb()

    jobs = []

    for i in range(NUM_WORKERS * JOBS_PER_WORKER):
        job = Job.create(
            task_name="print_message",
            payload={"message": f"contention test {i}"},
            priority=Priority.NORMAL,
        )

        enqueue(job)
        jobs.append(job)

    result_queue = multiprocessing.Queue()
    processes = []

    for _ in range(NUM_WORKERS):
        process = multiprocessing.Process(
            target=claim_jobs,
            args=(result_queue,),
        )

        process.start()
        processes.append(process)

    for process in processes:
        process.join(timeout=10)
        assert not process.is_alive()

    claimed = []

    for _ in range(NUM_WORKERS):
        claimed.extend(result_queue.get(timeout=5))

    claimed_ids = [job_id for job_id, _ in claimed]
    claimed_tokens = [
        token for _, token in claimed
    ]

    expected_ids = {job.id for job in jobs}

    # Every job should have been claimed.
    assert set(claimed_ids) == expected_ids

    # No job should have been claimed twice.
    assert len(claimed_ids) == len(set(claimed_ids))

    # Every execution should have its own token.
    assert len(claimed_tokens) == len(set(claimed_tokens))

    # Every claimed job should still be RUNNING.
    for job in jobs:
        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "RUNNING"

    # There should be no unclaimed jobs left in the ready queue.
    assert redis_client.llen("queue:default") == 0