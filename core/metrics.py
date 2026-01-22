import time
from redis_client import redis_client

METRICS_KEY = "metrics"


def incr(metric: str, value: int = 1):
    redis_client.hincrby(METRICS_KEY, metric, value)


def record_timing(metric: str, seconds: float):
    redis_client.hincrbyfloat(METRICS_KEY, metric, seconds)
    redis_client.hincrby(METRICS_KEY, f"{metric}_count", 1)


def snapshot():
    return redis_client.hgetall(METRICS_KEY)

if __name__ == "__main__":
    print("📊 ForgeQueue Metrics")
    for k, v in snapshot().items():
        print(f"{k}: {v}")
