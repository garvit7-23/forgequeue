import time

import pytest

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    dequeue,
    enqueue,
    acknowledge_job,
    recover_expired_jobs,
    PROCESSING_QUEUE,
)
from forgequeue.redis_client import redis_client


def test_stale_worker_cannot_ack_recovered_job():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "stale worker test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    # Worker A claims the job.
    result = dequeue()

    assert result is not None

    worker_a_job_id, worker_a_data, execution_token_a = result

    assert worker_a_job_id == job.id
    assert worker_a_data["status"] == "RUNNING"

    # Force the lease to expire.
    redis_client.zadd(
        PROCESSING_QUEUE,
        {job.id: time.time() - 1},
    )

    # Recovery returns the job to the ready queue
    # and invalidates Worker A's execution ownership.
    recovered = recover_expired_jobs()

    assert job.id in recovered

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    # Worker B claims the recovered job.
    result = dequeue()

    assert result is not None

    worker_b_job_id, worker_b_data, execution_token_b = result

    assert worker_b_job_id == job.id
    assert worker_b_data["status"] == "RUNNING"

    # The two executions must have different ownership.
    assert execution_token_a != execution_token_b

    # Worker A is stale and must not be able to
    # acknowledge Worker B's execution.
    with pytest.raises(ValueError):
        acknowledge_job(
            job.id,
            execution_token_a,
        )

    # The job must still belong to Worker B.
    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RUNNING"

    # Worker B can successfully acknowledge.
    acknowledge_job(
        job.id,
        execution_token_b,
    )

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "SUCCEEDED"