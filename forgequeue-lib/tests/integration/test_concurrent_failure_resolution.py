import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    RETRY_QUEUE,
    dequeue,
    enqueue,
    resolve_failed_job,
)
from forgequeue.core.retry import MAX_RETRIES
from forgequeue.redis_client import redis_client


def try_resolve_failure(
    job_id,
    execution_token,
    result_queue,
):
    try:
        result = resolve_failed_job(
            job_id,
            execution_token,
            1,
            time.time() + 60,
            MAX_RETRIES,
        )

        result_queue.put(result)

    except ValueError:
        result_queue.put("error")


def test_same_execution_can_only_be_resolved_for_retry_once():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "duplicate retry test"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    job_id, job_data, execution_token = result

    result_queue = multiprocessing.Queue()

    process_a = multiprocessing.Process(
        target=try_resolve_failure,
        args=(
            job_id,
            execution_token,
            result_queue,
        ),
    )

    process_b = multiprocessing.Process(
        target=try_resolve_failure,
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

    # Exactly one process should transition the execution
    # to RETRY_SCHEDULED.
    assert results.count(1) == 1
    assert results.count("error") == 1

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "RETRY_SCHEDULED"

    assert redis_client.hget(
        f"job:{job.id}",
        "execution_token",
    ) is None

    assert redis_client.zscore(
        PROCESSING_QUEUE,
        job.id,
    ) is None

    # Exactly one retry entry should exist.
    assert redis_client.zscore(
        RETRY_QUEUE,
        job.id,
    ) is not None

    assert redis_client.zcard(
        RETRY_QUEUE,
    ) == 1