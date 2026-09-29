from collections.abc import Callable
from typing import Any


TASK_REGISTRY: dict[str, Callable[[Any], Any]] = {}


def register_task(name: str, task: Callable[[Any], Any]):
    if name in TASK_REGISTRY:
        raise ValueError(
            f"Task already registered: {name}"
        )

    TASK_REGISTRY[name] = task


def get_task(name: str) -> Callable[[Any], Any]:
    try:
        return TASK_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown task: {name}"
        ) from None