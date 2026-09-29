import time
from forgequeue.redis_client import redis_client

METRICS_KEY = "metrics"


def incr(metric: str, value: int = 1):
    redis_client.hincrby(METRICS_KEY, metric, value)


def record_timing(metric: str, seconds: float):
    redis_client.hincrbyfloat(METRICS_KEY, metric, seconds)
    redis_client.hincrby(METRICS_KEY, f"{metric}_count", 1)


def snapshot():
    return redis_client.hgetall(METRICS_KEY)

def queue_depth():
    return {
        "high": redis_client.llen("queue:high"),
        "default": redis_client.llen("queue:default"),
        "low": redis_client.llen("queue:low"),
        "processing": redis_client.zcard("queue:processing"),
        "retry": redis_client.zcard("queue:retry"),
        "dead": redis_client.llen("queue:dead"),
    }

if __name__ == "__main__":
    print("ðŸ“Š ForgeQueue Metrics")
    for k, v in snapshot().items():
        print(f"{k}: {v}")

