from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import dequeue, enqueue
from forgequeue.redis_client import redis_client


def test_stale_queue_entry_does_not_hide_valid_job():
    redis_client.flushdb()

    stale_job_id = "stale-job-1"

    # Put an invalid/stale ID into the default queue.
    redis_client.lpush("queue:default", stale_job_id)

    # Create a valid job and put it behind the stale entry.
    job = Job.create(
        task_name="print_message",
        payload={"message": "valid job"},
        priority=Priority.NORMAL,
    )

    enqueue(job)

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

    # The stale entry must no longer remain.
    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == []

def test_terminal_job_entry_does_not_hide_valid_job():
    redis_client.flushdb()

    stale_job = Job.create(
        task_name="print_message",
        payload={"message": "already done"},
        priority=Priority.NORMAL,
    )

    enqueue(stale_job)

    # Simulate a stale ready-queue entry by making the job terminal.
    redis_client.hset(
        f"job:{stale_job.id}",
        "status",
        "SUCCEEDED",
    )

    valid_job = Job.create(
        task_name="print_message",
        payload={"message": "valid job"},
        priority=Priority.NORMAL,
    )

    enqueue(valid_job)

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == valid_job.id
    assert job_data["status"] == "RUNNING"

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == []