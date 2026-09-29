from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    dequeue,
    enqueue,
    resolve_failed_job,
    PROCESSING_QUEUE,
    DEAD_QUEUE,
)
from forgequeue.redis_client import redis_client


def test_failed_job_is_moved_to_dead_letter_queue():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "dead letter test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None
    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

    resolve_failed_job(
        job.id,
        execution_token=execution_token,
        retries=4,
        run_at=9999999999,
        max_retries=3,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "DEAD"

    assert int(
        redis_client.hget(
            f"job:{job.id}",
            "retries",
        )
    ) == 4

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None

    assert redis_client.lrange(
        DEAD_QUEUE,
        0,
        -1,
    ) == [job.id]