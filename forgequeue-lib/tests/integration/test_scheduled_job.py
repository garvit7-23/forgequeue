import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    schedule_job,
    dequeue,
)
from forgequeue.redis_client import redis_client
from forgequeue.scheduler.scheduler import (
    MOVE_DUE_JOB_SCRIPT,
    SCHEDULED_SET,
)


def test_due_scheduled_job_is_moved_to_ready_queue():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "scheduled test"},
        priority=Priority.NORMAL,
    )

    run_at = time.time() - 1

    schedule_job(job, run_at)

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "CREATED"

    assert redis_client.zscore(
        SCHEDULED_SET,
        job.id,
    ) is not None

    script = redis_client.register_script(MOVE_DUE_JOB_SCRIPT)

    result = script(
        keys=[SCHEDULED_SET],
        args=[job.id, time.time()],
    )

    assert result == 1

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    assert redis_client.zscore(
        SCHEDULED_SET,
        job.id,
    ) is None

    result = dequeue()

    assert result is not None

    claimed_job_id, job_data, execution_token = result

    assert claimed_job_id == job.id
    assert job_data["status"] == "RUNNING"

def test_future_scheduled_job_is_not_moved_to_ready_queue():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "future scheduled test"},
        priority=Priority.NORMAL,
    )

    run_at = time.time() + 60

    schedule_job(job, run_at)

    script = redis_client.register_script(MOVE_DUE_JOB_SCRIPT)

    result = script(
        keys=[SCHEDULED_SET],
        args=[job.id, time.time()],
    )

    assert result == 0

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "CREATED"

    assert redis_client.zscore(
        SCHEDULED_SET,
        job.id,
    ) is not None

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == []

def test_scheduled_job_is_not_enqueued_twice():
    redis_client.flushdb()

    job = Job.create(
        task_name="print_message",
        payload={"message": "duplicate schedule test"},
        priority=Priority.NORMAL,
    )

    schedule_job(job, time.time() - 1)

    script = redis_client.register_script(MOVE_DUE_JOB_SCRIPT)

    first_result = script(
        keys=[SCHEDULED_SET],
        args=[job.id, time.time()],
    )

    assert first_result == 1

    assert redis_client.hget(
        f"job:{job.id}",
        "status",
    ) == "QUEUED"

    second_result = script(
        keys=[SCHEDULED_SET],
        args=[job.id, time.time()],
    )

    assert second_result == 0

    assert redis_client.lrange(
        "queue:default",
        0,
        -1,
    ) == [job.id]

def test_invalid_scheduled_entry_does_not_hide_valid_job():
    redis_client.flushdb()

    stale_job_id = "stale-scheduled-job"

    redis_client.zadd(
        SCHEDULED_SET,
        {stale_job_id: time.time() - 1},
    )

    valid_job = Job.create(
        task_name="print_message",
        payload={"message": "valid scheduled job"},
        priority=Priority.NORMAL,
    )

    schedule_job(
        valid_job,
        time.time() - 1,
    )

    script = redis_client.register_script(MOVE_DUE_JOB_SCRIPT)

    stale_result = script(
        keys=[SCHEDULED_SET],
        args=[stale_job_id, time.time()],
    )

    assert stale_result == -1

    assert redis_client.zscore(
        SCHEDULED_SET,
        stale_job_id,
    ) is None

    valid_result = script(
        keys=[SCHEDULED_SET],
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