def print_message(payload):
    print(f"ðŸ“¨ Processing job: {payload['message']}")
def unstable_task(payload):
    if payload["fail"]:
        raise RuntimeError("Intentional failure")
    print("âœ… Task eventually succeeded")

