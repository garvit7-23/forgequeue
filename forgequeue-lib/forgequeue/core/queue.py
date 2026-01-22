import json
from forgequeue.redis_client import redis_client
from forgequeue.core.job import Job

# Priority execution queues (order matters)
QUEUES = [
    "queue:high",
    "queue:default",
    "queue:low",
]

# Other queues
RETRY_QUEUE = "queue:retry"
DEAD_QUEUE = "queue:dead"


def enqueue(job: Job):
    """
    Store job metadata and push job ID to priority queue
    """
    redis_client.hset(
        f"job:{job.id}",
        mapping=job.to_dict()
    )

    queue_name = f"queue:{job.priority.value}"
    redis_client.lpush(queue_name, job.id)


def dequeue():
    """
    Try queues in priority order: HIGH â†’ NORMAL â†’ LOW
    """
    for queue in QUEUES:
        job_id = redis_client.rpop(queue)
        if not job_id:
            continue

        job_data = redis_client.hgetall(f"job:{job_id}")
        if not job_data:
            return None

        # Deserialize fields
        job_data["payload"] = json.loads(job_data["payload"])
        job_data["retries"] = int(job_data["retries"])
        job_data["priority"] = job_data["priority"]

        return job_id, job_data

    return None


def move_to_dead(job_id: str):
    """
    Move permanently failed job to dead-letter queue
    """
    redis_client.lpush(DEAD_QUEUE, job_id)

