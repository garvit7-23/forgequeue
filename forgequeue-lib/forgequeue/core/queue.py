import json
from forgequeue.redis_client import redis_client
from forgequeue.core.job import Job, JobStatus
import time
import uuid

# Priority execution queues (order matters)
QUEUES = [
    "queue:high",
    "queue:default",
    "queue:low",
]

# Other queues
RETRY_QUEUE = "queue:retry"
DEAD_QUEUE = "queue:dead"
PROCESSING_QUEUE = "queue:processing"
LEASE_DURATION = 30

ENQUEUE_JOB_SCRIPT = """
local job_key = KEYS[1]
local queue_key = KEYS[2]

local status = redis.call('HGET', job_key, 'status')

if status then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'id', ARGV[1],
    'task_name', ARGV[2],
    'payload', ARGV[3],
    'priority', ARGV[4],
    'status', 'QUEUED',
    'retries', ARGV[5],
    'created_at', ARGV[6],
    'scheduled_at', ARGV[7],
    'cron', ARGV[8]
)

redis.call(
    'LPUSH',
    queue_key,
    ARGV[1]
)

return 1
"""
SCHEDULE_JOB_SCRIPT = """
local job_key = KEYS[1]
local scheduled_queue = KEYS[2]

local status = redis.call('HGET', job_key, 'status')

if status then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'id', ARGV[1],
    'task_name', ARGV[2],
    'payload', ARGV[3],
    'priority', ARGV[4],
    'status', 'CREATED',
    'retries', ARGV[5],
    'created_at', ARGV[6],
    'scheduled_at', ARGV[7],
    'cron', ARGV[8]
)

redis.call(
    'ZADD',
    scheduled_queue,
    ARGV[7],
    ARGV[1]
)

return 1
"""
REGISTER_CRON_SCRIPT = """
local job_key = KEYS[1]
local cron_hash = KEYS[2]

local status = redis.call('HGET', job_key, 'status')

if status then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'id', ARGV[1],
    'task_name', ARGV[2],
    'payload', ARGV[3],
    'priority', ARGV[4],
    'status', 'CREATED',
    'retries', ARGV[5],
    'created_at', ARGV[6],
    'scheduled_at', '',
    'cron', ARGV[7]
)

redis.call(
    'HSET',
    cron_hash,
    ARGV[1],
    ARGV[7]
)

return 1
"""
RENEW_LEASE_SCRIPT = """
local job_key = KEYS[1]
local processing_queue = KEYS[2]

local job_id = ARGV[1]
local execution_token = ARGV[2]
local lease_until = tonumber(ARGV[3])

local status = redis.call("HGET", job_key, "status")

if status ~= "RUNNING" then
    return 0
end

local stored_token = redis.call("HGET", job_key, "execution_token")

if stored_token ~= execution_token then
    return 0
end

local current_lease = redis.call(
    "ZSCORE",
    processing_queue,
    job_id
)

if not current_lease then
    return 0
end

redis.call(
    "ZADD",
    processing_queue,
    lease_until,
    job_id
)

return 1
"""

def register_cron_job(job: Job, cron_expression: str):
    data = job.to_dict()

    register_script = redis_client.register_script(REGISTER_CRON_SCRIPT)

    result = register_script(
        keys=[f"job:{job.id}", "queue:cron"],
        args=[
            data["id"],
            data["task_name"],
            data["payload"],
            data["priority"],
            data["retries"],
            data["created_at"],
            cron_expression,
        ],
    )

    if result != 1:
        raise ValueError(
            f"Cannot register cron job {job.id}: job already exists"
        )

def enqueue(job: Job):
    """
    Atomically store job metadata and push job ID
    to the appropriate priority queue.
    """

    job.transition_to(JobStatus.QUEUED)

    data = job.to_dict()

    enqueue_script = redis_client.register_script(
        ENQUEUE_JOB_SCRIPT
    )

    queue_name = f"queue:{job.priority.value}"

    result = enqueue_script(
        keys=[
            f"job:{job.id}",
            queue_name,
        ],
        args=[
            data["id"],
            data["task_name"],
            data["payload"],
            data["priority"],
            data["retries"],
            data["created_at"],
            data["scheduled_at"],
            data["cron"],
        ],
    )

    if result != 1:
        raise ValueError(
            f"Cannot enqueue job {job.id}: "
            f"job already exists"
        )


def schedule_job(job: Job, run_at: float):
    """
    Atomically store a delayed job and add it to the
    scheduled-job sorted set.
    """

    data = job.to_dict()

    schedule_script = redis_client.register_script(
        SCHEDULE_JOB_SCRIPT
    )

    result = schedule_script(
        keys=[
            f"job:{job.id}",
            "queue:scheduled",
        ],
        args=[
            data["id"],
            data["task_name"],
            data["payload"],
            data["priority"],
            data["retries"],
            data["created_at"],
            run_at,
            data["cron"],
        ],
    )

    if result != 1:
        raise ValueError(
            f"Cannot schedule job {job.id}: "
            f"job already exists"
        )

CLAIM_JOB_SCRIPT = """
local job_id = nil

while true do
    job_id = redis.call('RPOP', KEYS[1])

    if not job_id then
        return nil
    end

    local job_key = 'job:' .. job_id
    local status = redis.call('HGET', job_key, 'status')

    if status == 'QUEUED' then
        local lease_until = tonumber(ARGV[1])
        local execution_token = ARGV[2]

        redis.call(
            'ZADD',
            KEYS[2],
            lease_until,
            job_id
        )

        redis.call(
            'HSET',
            job_key,
            'status',
            'RUNNING',
            'execution_token',
            execution_token
        )

        return job_id
    end
end
"""

RECOVER_JOB_SCRIPT = """
local job_id = ARGV[1]
local now = tonumber(ARGV[2])
local job_key = 'job:' .. job_id
local status = redis.call('HGET', job_key, 'status')

if status ~= 'RUNNING' then
    redis.call('ZREM', KEYS[1], job_id)
    return 0
end

local lease = redis.call('ZSCORE', KEYS[1], job_id)

if not lease then
    return 0
end

if tonumber(lease) > now then
    return 0
end

local priority = redis.call('HGET',  job_key, 'priority')

if not priority then
    redis.call('ZREM', KEYS[1], job_id)
    return -1
end

redis.call('ZREM', KEYS[1], job_id)

redis.call(
    'HSET',
     job_key,
    'status',
    'QUEUED'
)
redis.call(
    'HDEL',
    'job:' .. job_id,
    'execution_token'
)

redis.call(
    'LPUSH',
    'queue:' .. priority,
    job_id
)

return 1
"""

def dequeue():
    """
    Atomically claim one job from the highest-priority ready queue.
    """

    claim_script = redis_client.register_script(
        CLAIM_JOB_SCRIPT
    )

    for queue in QUEUES:
        lease_until = time.time() + LEASE_DURATION
        execution_token = uuid.uuid4().hex

        job_id = claim_script(
            keys=[queue, PROCESSING_QUEUE],
            args=[
                lease_until,
                execution_token,
            ],
        )

        if not job_id:
            continue

        job_data = redis_client.hgetall(
            f"job:{job_id}"
        )

        if not job_data:
            return None

        job_data["payload"] = json.loads(
            job_data["payload"]
        )

        job_data["retries"] = int(
            job_data["retries"]
        )

        return job_id, job_data, execution_token

    return None

ACK_JOB_SCRIPT = """
local job_id = ARGV[1]
local execution_token = ARGV[2]

local job_key = 'job:' .. job_id

local status = redis.call(
    'HGET',
    job_key,
    'status'
)

if status ~= 'RUNNING' then
    return 0
end

local stored_token = redis.call(
    'HGET',
    job_key,
    'execution_token'
)

if stored_token ~= execution_token then
    return 0
end

redis.call(
    'HSET',
    job_key,
    'status',
    'SUCCEEDED'
)

redis.call(
    'HDEL',
    job_key,
    'execution_token'
)

redis.call(
    'ZREM',
    KEYS[1],
    job_id
)

return 1
"""

RESOLVE_FAILURE_SCRIPT = """
local job_id = ARGV[1]
local execution_token = ARGV[2]
local retries = tonumber(ARGV[3])
local run_at = tonumber(ARGV[4])
local max_retries = tonumber(ARGV[5])

local job_key = 'job:' .. job_id
local status = redis.call('HGET', job_key, 'status')

if status ~= 'RUNNING' then
    return 0
end

local stored_token = redis.call(
    'HGET',
    job_key,
    'execution_token'
)

if stored_token ~= execution_token then
    return 0
end

if retries <= max_retries then

    redis.call(
        'HSET',
        job_key,
        'status',
        'RETRY_SCHEDULED',
        'retries',
        retries
    )
        redis.call(
        'HDEL',
        job_key,
        'execution_token'
    )

    redis.call(
        'ZREM',
        KEYS[1],
        job_id
    )

    redis.call(
        'ZADD',
        KEYS[2],
        run_at,
        job_id
    )

    return 1

else

    redis.call(
        'HSET',
        job_key,
        'status',
        'DEAD',
        'retries',
        retries
    )
        redis.call(
        'HDEL',
        job_key,
        'execution_token'
    )

    redis.call(
        'ZREM',
        KEYS[1],
        job_id
    )

    redis.call(
        'LPUSH',
        KEYS[3],
        job_id
    )

    return 2
end
"""

def acknowledge_job(
    job_id: str,
    execution_token: str,
):
    """
    Atomically acknowledge successful execution
    only if this worker owns the current execution.
    """

    ack_script = redis_client.register_script(
        ACK_JOB_SCRIPT
    )

    result = ack_script(
        keys=[PROCESSING_QUEUE],
        args=[
            job_id,
            execution_token,
        ],
    )

    if result != 1:
        raise ValueError(
            f"Cannot acknowledge job {job_id}: "
            f"execution ownership is no longer valid"
        )

def renew_lease(job_id, execution_token):
    script = redis_client.register_script(RENEW_LEASE_SCRIPT)

    lease_until = time.time() + LEASE_DURATION

    result = script(
        keys=[
            f"job:{job_id}",
            PROCESSING_QUEUE,
        ],
        args=[
            job_id,
            execution_token,
            lease_until,
        ],
    )

    if int(result) != 1:
        raise ValueError(
            "Execution no longer owns the job lease"
        )

    return True

def recover_expired_jobs():
    """
    Recover jobs whose processing lease has expired.
    """

    now = time.time()

    expired_jobs = redis_client.zrangebyscore(
        PROCESSING_QUEUE,
        0,
        now,
    )

    recover_script = redis_client.register_script(
        RECOVER_JOB_SCRIPT
    )

    recovered = []

    for job_id in expired_jobs:
        result = recover_script(
            keys=[PROCESSING_QUEUE],
            args=[job_id, now],
        )

        if result == 1:
            recovered.append(job_id)

    return recovered

def resolve_failed_job(
    job_id: str,
    execution_token: str,
    retries: int,
    run_at: float,
    max_retries: int,
):
    script = redis_client.register_script(
        RESOLVE_FAILURE_SCRIPT
    )

    result = script(
        keys=[
            PROCESSING_QUEUE,
            RETRY_QUEUE,
            DEAD_QUEUE,
        ],
        args=[
            job_id,
            execution_token,
            retries,
            run_at,
            max_retries,
        ],
    )

    if result == 0:
        raise ValueError(
            f"Cannot resolve failure for job {job_id}: "
            f"job is not RUNNING"
        )

    return result
