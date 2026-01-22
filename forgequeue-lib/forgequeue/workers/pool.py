import multiprocessing
from forgequeue.workers.worker import run_worker
import signal
import sys


def start_worker_pool(num_workers: int):
    print(f"ðŸš€ Starting worker pool with {num_workers} workers")

    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(target=run_worker)
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

def shutdown_pool(signum, frame):
    print("ðŸ›‘ Shutting down worker pool...")
    for p in processes:
        p.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_pool)
signal.signal(signal.SIGTERM, shutdown_pool)

if __name__ == "__main__":
    start_worker_pool(num_workers=4)

