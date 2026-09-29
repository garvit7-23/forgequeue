from forgequeue.core.metrics import queue_depth
from forgequeue.redis_client import redis_client


def test_queue_depth_reports_current_redis_state():
    redis_client.flushdb()

    redis_client.rpush("queue:high", "job-1", "job-2")
    redis_client.rpush("queue:default", "job-3")
    redis_client.zadd(
        "queue:processing",
        {"job-4": 9999999999},
    )
    redis_client.zadd(
        "queue:retry",
        {"job-5": 9999999999},
    )
    redis_client.rpush("queue:dead", "job-6")

    depth = queue_depth()

    assert depth == {
        "high": 2,
        "default": 1,
        "low": 0,
        "processing": 1,
        "retry": 1,
        "dead": 1,
    }