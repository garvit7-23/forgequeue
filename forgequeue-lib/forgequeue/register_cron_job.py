from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import register_cron_job

# 1ï¸âƒ£ Create job metadata
job = Job.create(
    task_name="print_message",
    payload={"message": "Hello from cron"},
    priority=Priority.NORMAL
)

# IMPORTANT: use a stable ID for cron jobs
job_id = "cron-job-1"
job.id = job_id

register_cron_job(job, "* * * * *")

print(f"✅ Registered cron job: {job_id}")

