from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    dequeue,
    enqueue,
    acknowledge_job,
    PROCESSING_QUEUE,
)
from forgequeue.redis_client import redis_client


def test_acknowledge_marks_job_succeeded_and_removes_lease():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "ack test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is not None

    acknowledge_job(
        job.id,
        execution_token,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "SUCCEEDED"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None