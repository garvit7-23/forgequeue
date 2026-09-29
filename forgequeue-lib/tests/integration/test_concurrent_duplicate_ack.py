import multiprocessing

import pytest

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    acknowledge_job,
    dequeue,
    enqueue,
)
from forgequeue.redis_client import redis_client


def try_ack(job_id, execution_token, result_queue):
    try:
        acknowledge_job(
            job_id,
            execution_token,
        )
        result_queue.put(True)
    except ValueError:
        result_queue.put(False)


def test_same_execution_can_only_be_acknowledged_once():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "duplicate ack test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    job_id, job_data, execution_token = result

    result_queue = multiprocessing.Queue()

    process_a = multiprocessing.Process(
        target=try_ack,
        args=(
            job_id,
            execution_token,
            result_queue,
        ),
    )

    process_b = multiprocessing.Process(
        target=try_ack,
        args=(
            job_id,
            execution_token,
            result_queue,
        ),
    )

    process_a.start()
    process_b.start()

    process_a.join(timeout=10)
    process_b.join(timeout=10)

    assert not process_a.is_alive()
    assert not process_b.is_alive()

    results = [
        result_queue.get(timeout=5),
        result_queue.get(timeout=5),
    ]

    # Exactly one process owns the successful transition.
    assert results.count(True) == 1
    assert results.count(False) == 1

    # The job must end in SUCCEEDED.
    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "SUCCEEDED"

    # The execution token should be removed after ACK.
    assert redis_client.hget(
        f"job:{job.id}",
        "execution_token",
    ) is None

    # The processing lease should be gone.
    assert redis_client.zscore(
        "queue:processing",
        job.id,
    ) is None