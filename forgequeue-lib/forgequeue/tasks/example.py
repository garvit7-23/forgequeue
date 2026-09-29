def print_message(payload):
    print(f"ðŸ“¨ Processing job: {payload['message']}")
def unstable_task(payload):
    if payload["fail"]:
        raise RuntimeError("Intentional failure")
    print("âœ… Task eventually succeeded")

from forgequeue.core.task_registry import register_task

register_task("print_message", print_message)
register_task("unstable_task", unstable_task)

import time

def slow_task(payload):
    seconds = payload.get("seconds", 20)
    print(f"Slow task started for {seconds}s")
    time.sleep(seconds)
    print("Slow task finished")

register_task("slow_task", slow_task)