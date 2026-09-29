import time
from uuid6 import uuid7

from croniter import croniter

from forgequeue.redis_client import redis_client


CRON_HASH = "queue:cron"
CRON_NEXT = "queue:cron_next"


INITIALIZE_CRON_SCRIPT = """
local cron_next = KEYS[1]
local cron_job_id = ARGV[1]

local current = redis.call('ZSCORE', cron_next, cron_job_id)

if current then
    return 0
end

redis.call('ZADD', cron_next, 0, cron_job_id)

return 1
"""


CREATE_CRON_EXECUTION_SCRIPT = """
local cron_next = KEYS[1]
local job_key = KEYS[2]
local queue_key = KEYS[3]

local cron_job_id = ARGV[1]
local execution_id = ARGV[2]
local expected_next = tonumber(ARGV[3])
local next_ts = tonumber(ARGV[4])
local task_name = ARGV[5]
local payload = ARGV[6]
local priority = ARGV[7]
local created_at = ARGV[8]

local current_next = redis.call(
    'ZSCORE',
    cron_next,
    cron_job_id
)

if not current_next then
    return 0
end

if tonumber(current_next) ~= expected_next then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'id', execution_id,
    'task_name', task_name,
    'payload', payload,
    'priority', priority,
    'status', 'QUEUED',
    'retries', '0',
    'created_at', created_at,
    'scheduled_at', '',
    'cron', ''
)

redis.call(
    'LPUSH',
    queue_key,
    execution_id
)

redis.call(
    'ZADD',
    cron_next,
    next_ts,
    cron_job_id
)

return 1
"""


def run_cron_scheduler():
    print("🕒 Cron scheduler started...")

    initialize_cron = redis_client.register_script(
        INITIALIZE_CRON_SCRIPT
    )

    create_execution = redis_client.register_script(
        CREATE_CRON_EXECUTION_SCRIPT
    )

    while True:
        now = time.time()
        jobs = redis_client.hgetall(CRON_HASH)

        for job_id, expr in jobs.items():
            next_run = redis_client.zscore(CRON_NEXT, job_id)

            if next_run is None:
                initialize_cron(
                    keys=[CRON_NEXT],
                    args=[job_id],
                )
                continue

            if next_run > now:
                continue

            next_ts = croniter(expr, now).get_next(float)

            execution_id = str(uuid7())
            

            job_data = redis_client.hgetall(
                f"job:{job_id}"
            )

            if not job_data:
                continue

            queue_name = f"queue:{job_data['priority']}"

            result = create_execution(
                keys=[
                    CRON_NEXT,
                    f"job:{execution_id}",
                    queue_name,
                ],
                args=[
                    job_id,
                    execution_id,
                    next_run,
                    next_ts,
                    job_data["task_name"],
                    job_data["payload"],
                    job_data["priority"],
                    time.time(),
                ],
            )

            if result == 1:
                print(
                    f"🔁 Cron job {job_id} "
                    f"created execution {execution_id}"
                )

        time.sleep(5)


if __name__ == "__main__":
    run_cron_scheduler()
