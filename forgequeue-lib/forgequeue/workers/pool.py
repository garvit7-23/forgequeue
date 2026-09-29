import multiprocessing

from forgequeue.workers.worker import run_worker


def shutdown_pool(processes, shutdown_event):
    print(" Shutting down worker pool...")
    shutdown_event.set()

    for process in processes:
        process.join()

    print("Worker pool shut down gracefully")


def start_worker_pool(num_workers: int):
    print(f" Starting worker pool with {num_workers} workers")

    shutdown_event = multiprocessing.Event()

    processes = []

    for _ in range(num_workers):
        process = multiprocessing.Process(
            target=run_worker,
            args=(shutdown_event,),
        )
        process.start()
        processes.append(process)

    try:
        for process in processes:
            process.join()

    except KeyboardInterrupt:
        shutdown_pool(processes, shutdown_event)


if __name__ == "__main__":
    start_worker_pool(num_workers=4)