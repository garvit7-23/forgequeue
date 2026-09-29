import time

import pytest

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    acknowledge_job,
    dequeue,
    enqueue,
    recover_expired_jobs,
    resolve_failed_job,
)
from forgequeue.redis_client import redis_client


def test_stale_worker_cannot_resolve_failure_of_recovered_job():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "stale failure test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    # Worker A claims the job.
    result_a = dequeue()

    assert result_a is not None

    job_id_a, job_data_a, execution_token_a = result_a

    assert job_id_a == job.id
    assert job_data_a["status"] == "RUNNING"

    # Force Worker A's lease to expire.
    redis_client.zadd(
        PROCESSING_QUEUE,
        {job.id: time.time() - 1},
    )

    # Recover the expired execution.
    recovered = recover_expired_jobs()

    assert recovered == [job.id]

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    # Worker B claims the recovered job.
    result_b = dequeue()

    assert result_b is not None

    job_id_b, job_data_b, execution_token_b = result_b

    assert job_id_b == job.id
    assert job_data_b["status"] == "RUNNING"

    # The recovered execution must have a different ownership token.
    assert execution_token_a != execution_token_b

    # Worker A is now stale and must not be able to resolve
    # Worker B's execution as failed.
    with pytest.raises(ValueError):
        resolve_failed_job(
            job.id,
            execution_token_a,
            retries=1,
            run_at=time.time(),
            max_retries=3,
        )

    # Worker B's execution must remain untouched.
    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RUNNING"

    # Worker B can still successfully finish its own execution.
    acknowledge_job(
        job.id,
        execution_token_b,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "SUCCEEDED"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None