def print_message(payload):
    print(f"📨 Processing job: {payload['message']}")
def unstable_task(payload):
    if payload["fail"]:
        raise RuntimeError("Intentional failure")
    print("✅ Task eventually succeeded")