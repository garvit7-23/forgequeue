import multiprocessing
import time

from forgequeue.core.job import Job, Priority
from forgequeue.core.queue import (
    PROCESSING_QUEUE,
    dequeue,
    enqueue,
    recover_expired_jobs,
)
from forgequeue.redis_client import redis_client


NUM_JOBS = 50
NUM_RECOVERY_PROCESSES = 4


def recovery_loop(start_event, stop_event):
    start_event.wait()

    while not stop_event.is_set():
        recover_expired_jobs()


def test_claims_are_not_recovered_while_leases_are_fresh():
    redis_client.flushdb()

    jobs = []

    for i in range(NUM_JOBS):
        job = Job.create(
            task_name="print_message",
            payload={"message": f"race test {i}"},
            priority=Priority.NORMAL,
        )

        enqueue(job)
        jobs.append(job)

    start_event = multiprocessing.Event()
    stop_event = multiprocessing.Event()

    processes = []

    for _ in range(NUM_RECOVERY_PROCESSES):
        process = multiprocessing.Process(
            target=recovery_loop,
            args=(start_event, stop_event),
        )

        process.start()
        processes.append(process)

    claimed = []

    try:
        start_event.set()

        # Continuously claim jobs while recovery processes
        # are simultaneously checking PROCESSING_QUEUE.
        for _ in range(NUM_JOBS):
            result = dequeue()

            assert result is not None

            job_id, job_data, execution_token = result

            claimed.append(
                (
                    job_id,
                    execution_token,
                )
            )

            # Give recovery processes opportunities to race
            # against the freshly created lease.
            time.sleep(0.01)

        # Give the recovery processes a little more time to
        # observe the processing queue.
        time.sleep(0.5)

    finally:
        stop_event.set()

        for process in processes:
            process.join(timeout=5)

            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    assert len(claimed) == NUM_JOBS

    # Every job must still belong to its active execution.
    for job_id, execution_token in claimed:
        assert redis_client.hget(
            f"job:{job_id}",
            "status",
        ) == "RUNNING"

        assert redis_client.hget(
            f"job:{job_id}",
            "execution_token",
        ) == execution_token

        lease = redis_client.zscore(
            PROCESSING_QUEUE,
            job_id,
        )

        assert lease is not None
        assert lease > time.time()