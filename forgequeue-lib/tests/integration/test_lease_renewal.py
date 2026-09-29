import time

import pytest

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    dequeue,
    enqueue,
    recover_expired_jobs,
    renew_lease,
)
from forgequeue.redis_client import redis_client


def test_current_worker_can_renew_its_lease():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 60},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    job_id, job_data, execution_token = result

    assert job_id == job.id
    assert job_data["status"] == "RUNNING"

    original_lease = redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    )

    assert original_lease is not None

    renewed = renew_lease(
        job.id,
        execution_token,
    )

    assert renewed is True

    renewed_lease = redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    )

    assert renewed_lease is not None
    assert renewed_lease > original_lease


def test_stale_worker_cannot_renew_recovered_execution():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 60},
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

    # Recover Worker A's execution.
    recovered = recover_expired_jobs()

    assert recovered == [job.id]

    # Worker B claims the recovered job.
    result_b = dequeue()

    assert result_b is not None

    job_id_b, job_data_b, execution_token_b = result_b

    assert job_id_b == job.id
    assert job_data_b["status"] == "RUNNING"
    assert execution_token_a != execution_token_b

    # Worker A is stale and must not renew Worker B's lease.
    with pytest.raises(ValueError):
        renew_lease(
            job.id,
            execution_token_a,
        )

    # Worker B's lease must still exist.
    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is not None

def test_renewed_lease_is_not_recovered():
    redis_client.flushdb()

    job = Job.create(
        task_name="slow_task",
        payload={"seconds": 60},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    job_id, job_data, execution_token = result

    assert job_id == job.id
    assert job_data["status"] == "RUNNING"

    # Simulate the worker renewing its lease.
    assert renew_lease(
        job.id,
        execution_token,
    ) is True

    # Recovery should not see this execution as expired.
    recovered = recover_expired_jobs()

    assert recovered == []

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RUNNING"

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is not None