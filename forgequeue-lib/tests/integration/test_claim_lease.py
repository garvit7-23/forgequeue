import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import dequeue, PROCESSING_QUEUE
from forgequeue.redis_client import redis_client


def test_claim_creates_processing_lease():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "lease test"},
        priority=Priority.NORMAL,
    )

    from forgequeue.core.queue import enqueue

    enqueue(job)

    before = time.time()
    result = dequeue()
    after = time.time()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

    lease_until = redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    )

    assert lease_until is not None
    assert before + 29 <= lease_until <= after + 31

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == []