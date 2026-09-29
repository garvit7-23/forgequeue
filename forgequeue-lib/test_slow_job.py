from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import enqueue


job = Job.create(
    task_name="slow_task",
    payload={"seconds": 20},
    priority=Priority.NORMAL,
)

enqueue(job)

print("Job ID:", job.id)
