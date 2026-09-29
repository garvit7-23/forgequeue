from concurrent.futures import ThreadPoolExecutor

from forgequeue.core.job import Job
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    dequeue,
    enqueue,
    redis_client,
)


def _dequeue(_):
    return dequeue()


def test_concurrent_claim_only_one_worker_succeeds():
    redis_client.flushdb()

    job = Job.create(
        task_name="test_task",
        payload={"value": 123},
    )

    enqueue(job)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_dequeue, range(8)))

    successful = [result for result in results if result is not None]

    assert len(successful) == 1

    claimed_id, job_data, execution_token = successful[0]

    assert claimed_id == job.id
    assert job_data["status"] == "RUNNING"

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RUNNING"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is not None