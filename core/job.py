from dataclasses import dataclass, asdict
from enum import Enum
from uuid6 import uuid7
from time import time
from typing import Optional

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


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
            status=JobStatus.PENDING,
            retries=0,
            created_at=time(),
        )

    def to_dict(self):
        data = asdict(self)
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        data["scheduled_at"] = data["scheduled_at"] or ""
        data["cron"] = data["cron"] or ""
        return data

