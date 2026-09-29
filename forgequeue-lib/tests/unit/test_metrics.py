from forgequeue.core.metrics import (
    incr,
    record_timing,
    snapshot,
)
from forgequeue.redis_client import redis_client


def test_metrics_increment_and_timing():
    redis_client.flushdb()

    incr("jobs_processed")
    incr("jobs_processed")
    incr("jobs_failed", 2)

    record_timing("job_exec_time", 1.5)
    record_timing("job_exec_time", 2.5)

    metrics = snapshot()

    assert int(metrics["jobs_processed"]) == 2
    assert int(metrics["jobs_failed"]) == 2

    assert float(metrics["job_exec_time"]) == 4.0
    assert int(metrics["job_exec_time_count"]) == 2