from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import dequeue, enqueue
from forgequeue.redis_client import redis_client

def test_priority_ordering():
    redis_client.flushdb()

    low_job = Job.create(
        task_name="print_message",
        payload={"message": "low"},
        priority=Priority.LOW,
    )
    high_job = Job.create(
        task_name="print_message",
        payload={"message": "high"},
        priority=Priority.HIGH,
    )
    normal_job = Job.create(
        task_name="print_message",
        payload={"message": "normal"},
        priority=Priority.NORMAL,
    )

    enqueue(low_job)
    enqueue(high_job)
    enqueue(normal_job)

    first = dequeue()
    second = dequeue()
    third = dequeue()

    assert first is not None
    assert second is not None
    assert third is not None

    assert first[0] == high_job.id
    assert second[0] == normal_job.id
    assert third[0] == low_job.id