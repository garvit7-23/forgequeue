import time

from forgequeue.redis_client import redis_client
from forgequeue.core.job import JobStatus


RETRY_QUEUE = "queue:retry"
BASE_DELAY = 2
MAX_RETRIES = 3
MAX_DELAY = 60


SCHEDULE_RETRY_SCRIPT = """
local job_id = ARGV[1]
local retries = ARGV[2]
local run_at = tonumber(ARGV[3])

local job_key = 'job:' .. job_id

local status = redis.call('HGET', job_key, 'status')

if status ~= 'FAILED' then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'status',
    'RETRY_SCHEDULED',
    'retries',
    retries
)

redis.call(
    'ZADD',
    KEYS[1],
    run_at,
    job_id
)

return 1
"""
def calculate_retry_delay(retries: int) -> int:
    return min(
        BASE_DELAY * (2 ** retries),
        MAX_DELAY,
    )


def schedule_retry(job_id: str, retries: int):
    if retries > MAX_RETRIES:
        raise ValueError(
            f"Retry limit exceeded for job {job_id}: "
            f"{retries} > {MAX_RETRIES}"
        )

    delay = calculate_retry_delay(retries)
    run_at = time.time() + delay

    schedule_script = redis_client.register_script(
        SCHEDULE_RETRY_SCRIPT
    )

    result = schedule_script(
        keys=[RETRY_QUEUE],
        args=[job_id, retries, run_at],
    )

    if result != 1:
        raise ValueError(
            f"Cannot schedule retry for job {job_id}: "
            f"job is not FAILED"
        )