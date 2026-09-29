import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    dequeue,
    enqueue,
    recover_expired_jobs,
)
from forgequeue.redis_client import redis_client


def test_running_job_can_be_recovered_after_lease_expires():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 60},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    # Worker claims the job.
    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"
    assert execution_token

    # Simulate the worker still executing after its lease expires.
    redis_client.zadd(
        PROCESSING_QUEUE,
        {job.id: time.time() - 1},
    )

    # The current system considers the execution abandoned
    # even though the worker could still be running.
    recovered = recover_expired_jobs()

    assert recovered == [job.id]

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None