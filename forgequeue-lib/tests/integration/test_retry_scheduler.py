import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    enqueue,
    dequeue,
    resolve_failed_job,
    RETRY_QUEUE,
)
from forgequeue.redis_client import redis_client
from forgequeue.scheduler.retry_scheduler import (
    MOVE_RETRY_SCRIPT,
)


def test_due_retry_is_moved_back_to_ready_queue():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "retry scheduler test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    resolve_failed_job(
        job.id,
        execution_token=execution_token,
        retries=1,
        run_at=time.time() - 1,
        max_retries=3,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    script = redis_client.register_script(MOVE_RETRY_SCRIPT)

    result = script(
        keys=[RETRY_QUEUE],
        args=[job.id, time.time()],
    )

    assert result == 1

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    assert redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    ) is None

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"