import time

from forgequeue.redis_client import redis_client

RETRY_QUEUE = "queue:retry"

MOVE_RETRY_SCRIPT = """
local job_id = ARGV[1]
local now = tonumber(ARGV[2])

local retry_at = redis.call('ZSCORE', KEYS[1], job_id)

if not retry_at then
    return 0
end

if tonumber(retry_at) > now then
    return 0
end

local job_key = 'job:' .. job_id
local status = redis.call('HGET', job_key, 'status')

if status ~= 'RETRY_SCHEDULED' then
    return 0
end

local priority = redis.call('HGET', job_key, 'priority')

if not priority then
    return -1
end

redis.call(
    'ZREM',
    KEYS[1],
    job_id
)

redis.call(
    'HSET',
    job_key,
    'status',
    'QUEUED'
)

redis.call(
    'LPUSH',
    'queue:' .. priority,
    job_id
)

return 1
"""


def run_retry_scheduler():
    print("⏱️ Retry scheduler started...")

    move_retry_script = redis_client.register_script(
        MOVE_RETRY_SCRIPT
    )

    while True:
        now = time.time()

        ready = redis_client.zrangebyscore(
            RETRY_QUEUE,
            0,
            now,
            start=0,
            num=1,
        )

        if not ready:
            time.sleep(1)
            continue

        job_id = ready[0]

        result = move_retry_script(
            keys=[RETRY_QUEUE],
            args=[job_id , now],
        )

        if result == 1:
            print(f"🔁 Retrying job {job_id}")

if __name__ == "__main__":
    run_retry_scheduler()