📦 ForgeQueue

Distributed Background Job Queue & Scheduler (Python + Redis)

ForgeQueue is a production-style background job processing system built from scratch using Python and Redis.
It supports asynchronous execution, retries with exponential backoff, priority queues, delayed jobs, cron-based scheduling, graceful shutdown, and metrics.

This project demonstrates real backend systems engineering, not just CRUD APIs.

🚀 Features

✅ Asynchronous background job execution

✅ Redis-backed persistent job storage

✅ Priority queues (HIGH / NORMAL / LOW)

✅ Multiprocessing worker pool

✅ Automatic retries with exponential backoff

✅ Dead-letter queue (DLQ) for failed jobs

✅ Delayed (run-at) jobs

✅ Cron-based recurring jobs

✅ Graceful worker shutdown (SIGINT / SIGTERM)

✅ Redis-backed operational metrics

✅ Dockerized Redis (production-like setup)

🧠 Why ForgeQueue?

Most applications require background processing for:

Emails & notifications

Payment verification

Data processing

Scheduled tasks

Long-running jobs

ForgeQueue is a minimal but correct implementation of how real systems like Celery, Sidekiq, and BullMQ work internally.

🏗️ System Architecture
High-Level Flow
Client / Producer
       |
       |  create job
       v
 Redis (job:{id})
       |
       | enqueue job_id
       v
Priority Queues
(high / default / low)
       |
       v
Worker Pool (multiprocessing)
       |
       | execute task
       |
Success        Failure
   |               |
   v               v
 DONE        Retry Queue (ZSET)
                  |
                  v
          Delayed retry → queue
                  |
              retries exceeded
                  |
                  v
            Dead Letter Queue

Scheduler Architecture

Delayed Jobs (ZSET)      Cron Jobs (HASH)
        |                      |
        | time reached         | cron tick
        v                      v
   Scheduler             Cron Scheduler
        |                      |
        +------ enqueue job_id +
                    |
                    v
              Priority Queues

forgequeue/
├── core/
│   ├── job.py          # Job model & enums
│   ├── queue.py        # Queue abstraction
│   ├── retry.py        # Retry scheduling
│   ├── metrics.py      # Redis-backed metrics
│   └── __init__.py
│
├── workers/
│   ├── worker.py       # Worker logic + shutdown + metrics
│   ├── pool.py         # Multiprocessing worker pool
│   └── __init__.py
│
├── scheduler/
│   ├── scheduler.py    # Delayed job scheduler
│   ├── cron_scheduler.py
│   └── __init__.py
│
├── tasks/
│   └── example.py      # Example tasks
│
├── redis_client.py
├── main.py             # Demo entry point
├── show_metrics.py
└── README.md

⚙️ Setup & Installation
1️⃣ Start Redis (Docker – Recommended)

docker run -d -p 6379:6379 --name forgequeue-redis redis

2️⃣ Install Python Dependencies

pip install redis uuid6 croniter

▶️ Running ForgeQueue

Terminal 1 – Worker Pool
python -m workers.pool

Terminal 2 – Delayed Job Scheduler
python -m scheduler.scheduler

Terminal 3 – Cron Scheduler
python -m scheduler.cron_scheduler

Terminal 4 – Enqueue Jobs
python main.py

⏱️ Metrics & Observability

View live metrics:

python -m core.metrics


Example output:

ForgeQueue Metrics
jobs_processed: 19
job_exec_time: 0.027
job_exec_time_count: 19


Average execution time:

avg = job_exec_time / job_exec_time_count

🛑 Graceful Shutdown

Press Ctrl + C on the worker pool:

🛑 Worker received shutdown signal
👷 Worker shutting down gracefully


✔ In-flight jobs complete
✔ No new jobs pulled
✔ Safe restart

🧪 Failure Handling

Failed jobs retry automatically (exponential backoff)

Retry limit enforced

Poison jobs moved to Dead Letter Queue

No job loss

🧠 Design Principles

Job metadata is immutable (except status & retries)

Schedulers only enqueue job IDs

Workers are stateless

Redis is the source of truth

Failure is expected and handled

🔮 Future Improvements

Job timeouts

Worker heartbeats

Prometheus metrics export

Web dashboard

Exactly-once execution

Rate limiting

🏁 Final Note

ForgeQueue was built to demonstrate real backend systems thinking:

concurrency

reliability

fault tolerance

observability

This is not a toy project — it’s a mini infrastructure component.

⭐ If you like this project

Give it a ⭐ and feel free to fork or extend it.

flowchart TD
    A[Producer] --> B[Redis Job Hash]
    B --> C[Priority Queues]
    C --> D[Worker Pool]

    D -->|Success| E[Done]
    D -->|Failure| F[Retry Queue]
    F -->|Backoff| C
    F -->|Max Retries| G[Dead Letter Queue]

    H[Delayed Scheduler] --> C
    I[Cron Scheduler] --> C
