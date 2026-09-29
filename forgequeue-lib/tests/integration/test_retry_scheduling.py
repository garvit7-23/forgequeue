import time
import pytest

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    dequeue,
    enqueue,
    resolve_failed_job,
    RETRY_QUEUE,
    PROCESSING_QUEUE,
)
from forgequeue.redis_client import redis_client
from forgequeue.scheduler.retry_scheduler import MOVE_RETRY_SCRIPT


def test_failed_job_is_scheduled_for_retry():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "retry test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None
    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

    run_at = time.time() + 10

    resolve_failed_job(
        job.id,
        execution_token=execution_token,
        retries=1,
        run_at=run_at,
        max_retries=3,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    assert int(
        redis_client.hget(
            f"job:{job.id}",
            "retries",
        )
    ) == 1

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None

    retry_timestamp = redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    )

    assert retry_timestamp is not None
    assert abs(retry_timestamp - run_at) < 1

def test_failed_job_cannot_be_resolved_twice():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "duplicate failure test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    run_at = time.time() + 10

    resolve_failed_job(
        job.id,
        execution_token=execution_token,
        retries=1,
        run_at=run_at,
        max_retries=3,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    retry_score = redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    )

    assert retry_score is not None

    with pytest.raises(ValueError):
        resolve_failed_job(
            job.id,
            execution_token=execution_token,
            retries=2,
            run_at=time.time() + 20,
            max_retries=3,
        )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    assert redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    ) == retry_score

def test_future_retry_is_not_moved_to_ready_queue():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "future retry test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()
    assert result is not None

    claimed_job_id, job_data, execution_token = result

    run_at = time.time() + 60

    resolve_failed_job(
        job.id,
        execution_token=execution_token,
        retries=1,
        run_at=run_at,
        max_retries=3,
    )

    script = redis_client.register_script(MOVE_RETRY_SCRIPT)

    result = script(
        keys=[RETRY_QUEUE],
        args=[job.id, time.time()],
    )

    assert result == 0

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    assert redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    ) is not None

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == []

def test_invalid_retry_entry_does_not_affect_valid_retry():
    redis_client.flushdb()

    stale_job_id = "stale-retry-job"

    redis_client.hset(
        f"job:{stale_job_id}",
        mapping={
            "status": "RETRY_SCHEDULED",
        },
    )

    redis_client.zadd(
        RETRY_QUEUE,
        {stale_job_id: time.time() - 1},
    )

    valid_job = Job.create(
        task_name="print_message",
        payload={"message": "valid retry"},
        priority=Priority.NORMAL,
    )

    enqueue(valid_job)

    result = dequeue()
    assert result is not None

    claimed_job_id, job_data, execution_token = result

    resolve_failed_job(
        valid_job.id,
        execution_token=execution_token,
        retries=1,
        run_at=time.time() - 1,
        max_retries=3,
    )

    script = redis_client.register_script(MOVE_RETRY_SCRIPT)

    stale_result = script(
        keys=[RETRY_QUEUE],
        args=[stale_job_id, time.time()],
    )

    assert stale_result == -1

  

    valid_result = script(
        keys=[RETRY_QUEUE],
        args=[valid_job.id, time.time()],
    )

    assert valid_result == 1

    assert redis_client.hget(
        f"job:{valid_job.id}",
        "status",
    ) == "QUEUED"

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == [valid_job.id]
