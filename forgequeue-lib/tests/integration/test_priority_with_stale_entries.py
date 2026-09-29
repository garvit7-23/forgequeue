from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import dequeue, enqueue
from forgequeue.redis_client import redis_client


def test_priority_ordering_with_stale_entries():
    redis_client.flushdb()

    stale_job = Job.create(
        task_name="print_message",
        payload={"message": "stale"},
        priority=Priority.HIGH,
    )
    enqueue(stale_job)

    redis_client.hset(
        f"job:{stale_job.id}",
        "status",
        "SUCCEEDED",
    )

    normal_job = Job.create(
        task_name="print_message",
        payload={"message": "normal"},
        priority=Priority.NORMAL,
    )

    high_job = Job.create(
        task_name="print_message",
        payload={"message": "high"},
        priority=Priority.HIGH,
    )

    low_job = Job.create(
        task_name="print_message",
        payload={"message": "low"},
        priority=Priority.LOW,
    )

    enqueue(normal_job)
    enqueue(high_job)
    enqueue(low_job)

    first = dequeue()
    second = dequeue()
    third = dequeue()

    assert first is not None
    assert second is not None
    assert third is not None

    assert first[0] == high_job.id
    assert second[0] == normal_job.id
    assert third[0] == low_job.id

    assert redis_client.lrange("queue:high", 0, -1) == []
    assert redis_client.lrange("queue:default", 0, -1) == []
    assert redis_client.lrange("queue:low", 0, -1) == []