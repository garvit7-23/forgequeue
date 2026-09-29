from forgequeue.core.metrics import (
    incr,
    queue_depth,
    record_timing,
    snapshot,
)
from forgequeue.redis_client import redis_client


def test_metrics_snapshot_contains_history_and_current_depth():
    redis_client.flushdb()

    incr("jobs_processed", 3)
    incr("jobs_failed", 1)
    record_timing("job_exec_time", 2.0)
    record_timing("job_exec_time", 4.0)

    redis_client.rpush(
        "queue:default",
        "job-1",
        "job-2",
    )

    redis_client.zadd(
        "queue:processing",
        {"job-3": 9999999999},
    )

    metrics = snapshot()
    depth = queue_depth()

    assert int(metrics["jobs_processed"]) == 3
    assert int(metrics["jobs_failed"]) == 1

    assert float(metrics["job_exec_time"]) == 6.0
    assert int(metrics["job_exec_time_count"]) == 2

    assert depth["default"] == 2
    assert depth["processing"] == 1