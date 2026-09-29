import time

from forgequeue.redis_client import redis_client


SCHEDULED_SET = "queue:scheduled"


MOVE_DUE_JOB_SCRIPT = """
local scheduled_queue = KEYS[1]

local job_id = ARGV[1]
local now = tonumber(ARGV[2])

local job_key = 'job:' .. job_id

local scheduled_at = redis.call('ZSCORE', scheduled_queue, job_id)

if not scheduled_at then
    return 0
end

if tonumber(scheduled_at) > now then
    return 0
end

local status = redis.call('HGET', job_key, 'status')
local priority = redis.call('HGET', job_key, 'priority')

if not status or not priority then
    redis.call('ZREM', scheduled_queue, job_id)
    return -1
end

if status ~= 'CREATED' then
    redis.call('ZREM', scheduled_queue, job_id)
    return -1
end

redis.call('ZREM', scheduled_queue, job_id)

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


def run_scheduler():
    print("⏰ Scheduler started (delayed jobs)...")

    move_due_job = redis_client.register_script(MOVE_DUE_JOB_SCRIPT)

    while True:
        now = time.time()

        due = redis_client.zrangebyscore(
            SCHEDULED_SET,
            0,
            now,
            start=0,
            num=1,
        )

        if not due:
            time.sleep(1)
            continue

        job_id = due[0]

        result = move_due_job(
            keys=[SCHEDULED_SET],
            args=[job_id, now],
        )

        if result == 1:
            print(f"⏳ Scheduled job {job_id} enqueued")


if __name__ == "__main__":
    run_scheduler()