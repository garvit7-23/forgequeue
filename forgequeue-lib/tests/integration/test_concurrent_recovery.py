import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    dequeue,
    enqueue,
    recover_expired_jobs,
)
from forgequeue.redis_client import redis_client


NUM_JOBS = 20
NUM_RECOVERY_WORKERS = 4


def recover_jobs(result_queue):
    recovered = recover_expired_jobs()
    result_queue.put(recovered)


def test_concurrent_recovery_does_not_recover_same_execution_twice():
    redis_client.flushdb()

    jobs = []

    for i in range(NUM_JOBS):
        job = Job.create(
            task_name="print_message",
            payload={"message": f"recovery test {i}"},
            priority=Priority.NORMAL,
        )

        enqueue(job)
        jobs.append(job)

    # Claim every job so that they are in PROCESSING.
    claimed = []

    for _ in range(NUM_JOBS):
        result = dequeue()

        assert result is not None

        job_id, job_data, execution_token = result

        claimed.append(
            (
                job_id,
                execution_token,
            )
        )

    assert len(claimed) == NUM_JOBS

    # Expire every lease.
    for job_id, _ in claimed:
        redis_client.zadd(
            PROCESSING_QUEUE,
            {job_id: time.time() - 1},
        )

    result_queue = multiprocessing.Queue()
    processes = []

    for _ in range(NUM_RECOVERY_WORKERS):
        process = multiprocessing.Process(
            target=recover_jobs,
            args=(result_queue,),
        )

        process.start()
        processes.append(process)

    for process in processes:
        process.join(timeout=10)
        assert not process.is_alive()

    all_recovered = []

    for _ in range(NUM_RECOVERY_WORKERS):
        all_recovered.extend(
            result_queue.get(timeout=5)
        )

    # Every expired execution should have been recovered exactly once.
    assert set(all_recovered) == {
        job_id for job_id, _ in claimed
    }

    assert len(all_recovered) == NUM_JOBS

    # Every job should now be QUEUED.
    for job in jobs:
        assert redis_client.hget(
            f"job:{job.id}",
            "status",
        ) == "QUEUED"

    # No processing leases should remain.
    assert redis_client.zcard(PROCESSING_QUEUE) == 0

    # Every job should be back in the ready queue.
    assert redis_client.llen("queue:default") == NUM_JOBS