from dataclasses import dataclass, asdict
from enum import Enum
from uuid6 import uuid7
from time import time
from typing import Optional

class JobStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DEAD = "DEAD"
    CANCELLED = "CANCELLED"


class Priority(str, Enum):
    HIGH = "high"
    NORMAL = "default"
    LOW = "low"


@dataclass
class Job:
    id: str
    task_name: str
    payload: dict
    priority: Priority
    status: JobStatus
    retries: int
    created_at: float
    scheduled_at: Optional[float] = None
    cron: Optional[str] = None

    @staticmethod
    def create(
        task_name: str,
        payload: dict,
        priority: Priority = Priority.NORMAL
    ):
        return Job(
            id=str(uuid7()),
            task_name=task_name,
            payload=payload,
            priority=priority,
            status=JobStatus.CREATED,
            retries=0,
            created_at=time(),
        )

    def transition_to(self, new_status: JobStatus):
        allowed_transitions = {
            JobStatus.CREATED: {
                JobStatus.QUEUED,
                JobStatus.CANCELLED,
            },
            JobStatus.QUEUED: {
                JobStatus.RUNNING,
                JobStatus.CANCELLED,
            },
            JobStatus.RUNNING: {
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
            },
            JobStatus.FAILED: {
                JobStatus.RETRY_SCHEDULED,
                JobStatus.DEAD,
            },
            JobStatus.RETRY_SCHEDULED: {
                JobStatus.QUEUED,
            },
            JobStatus.SUCCEEDED: set(),
            JobStatus.DEAD: set(),
            JobStatus.CANCELLED: set(),
        }

        if new_status not in allowed_transitions[self.status]:
            raise ValueError(
                f"Invalid job state transition: "
                f"{self.status.value} -> {new_status.value}"
            )

        self.status = new_status

   
    def to_dict(self):
        import json

        data = asdict(self)
        data["status"] = self.status.value
        data["priority"] = self.priority.value

        # Redis can't store dict directly -> store JSON string
        data["payload"] = json.dumps(self.payload)

        data["scheduled_at"] = data["scheduled_at"] or ""
        data["cron"] = data["cron"] or ""
        return data
