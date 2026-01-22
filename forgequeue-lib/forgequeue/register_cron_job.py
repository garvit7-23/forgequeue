import json
from forgequeue.redis_client import redis_client
from forgequeue.core.job import Job, Priority

# 1ï¸âƒ£ Create job metadata
job = Job.create(
    task_name="print_message",
    payload={"message": "Hello from cron"},
    priority=Priority.NORMAL
)

# IMPORTANT: use a stable ID for cron jobs
job_id = "cron-job-1"
job.id = job_id

job.payload = json.dumps(job.payload)

# Store job hash in Redis
redis_client.hset(
    f"job:{job_id}",
    mapping=job.to_dict()
)

print(f"âœ… Created cron job metadata: job:{job_id}")

