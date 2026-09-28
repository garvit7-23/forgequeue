# 📦 ForgeQueue

> ⚙️ **A Redis-backed distributed background job queue and scheduler implemented in Python.**

ForgeQueue is a systems-oriented implementation of background job processing, designed to explore the correctness problems that arise when jobs are executed concurrently, workers fail, leases expire, and executions are retried or rescheduled.

The implementation uses **Redis, Lua scripts, Python multiprocessing, and scheduled execution** to coordinate job state, queue ownership, retries, recovery, and worker execution.

The project focuses on the mechanisms behind reliable background processing rather than providing a feature-complete replacement for established queueing systems.

**🛠️ Stack:** Python · Redis · Lua · Multiprocessing · pytest
---

## Overview

Background job processing becomes a distributed coordination problem when multiple workers execute jobs concurrently and workers can fail while holding work.

ForgeQueue is a Python and Redis implementation that explores these failure and concurrency mechanisms directly. Jobs have explicit lifecycle states, workers acquire time-bounded leases, and each execution is assigned an execution_token that fences stale workers after ownership changes.

The system also implements priority queues, retry scheduling with exponential backoff, delayed jobs, cron scheduling, worker recovery, graceful shutdown, and lightweight operational metrics.
 
The project is intentionally scoped as a systems implementation for studying queue semantics and failure handling, rather than as a production replacement for established task-processing frameworks.

---

## 🧠 Problem And Design Goals

A basic queue can be modeled as:
```
Producer → Queue → Worker → Task
```

---

The correctness problem begins when execution is no longer reliable.

Consider a worker that:

- claims a job,

-  begins executing it,

- stops making progress,

- loses its lease,

- and is replaced by another worker.

The system must allow the second worker to recover the job without allowing the original worker to later mutate the state of the new execution.

Similar races occur when acknowledgement, failure resolution, and recovery happen concurrently.

ForgeQueue therefore focuses on four related problems:

- Atomic ownership: prevent concurrent workers from claiming the same execution.

- Failure recovery: make abandoned executions recoverable after lease expiration.

- Stale-worker fencing: prevent an old execution from modifying a newer execution.

- Scheduling correctness: ensure retries and scheduled jobs become eligible at the intended time without duplicate enqueueing.

###  Design goals

The implementation aims for:

| Goal | Mechanism |
| --- | --- |
| Explicit lifecycle | Job state machine |
| Atomic claiming | Redis Lua script |
| Crash recovery | Processing leases |
| Execution fencing | Per-execution token |
| Retry scheduling | Redis sorted set + backoff |
| Priority | Separate ready queues |
| Concurrent safety | Atomic state transitions + integration tests |
| Operational visibility | Redis-backed counters and queue-depth metrics |

## 🏗️ System Architecture

ForgeQueue separates four concerns:

```
                    ┌─────────────────┐
                    │    Producer     │
                    └────────┬────────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │         Redis         │
                 │                       │
                 │  Job state            │
                 │  Ready queues         │
                 │  Processing leases    │
                 │  Retry schedule       │
                 │  Scheduled jobs       │
                 │  Dead-letter queue    │
                 │  Metrics              │
                 └───────┬───────┬───────┘
                         │       │
                ┌────────┘       └─────────┐
                ▼                          ▼
          Worker Pool                 Schedulers
                │                          │
                ▼                          │
          Task Registry ◄──────────────────┘
                │
                ▼
             Task code

```
### Component responsibilities

#### Redis
Stores job state and provides the atomic primitives used for queue coordination.
#### Worker pool
Claims jobs, executes registered tasks, renews leases, acknowledges successful executions, and resolves failures.
#### Schedulers
Move delayed and retryable work into ready queues and manage recurring cron schedules.
#### Task registry
Maps task names stored in jobs to executable Python callables.
---


## 🗂️ Core Design & Correctness Mechanisms

### Job Lifecycle & State Model
Each job has an explicit lifecycle rather than relying solely on queue membership.

A simplified lifecycle is:

```
                ┌──────────┐
                │  QUEUED  │
                └────┬─────┘
                     │ claim
                     ▼
                ┌──────────┐
                │ RUNNING  │
                └────┬─────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
       success     failure    lease
          │          │        expires
          ▼          ▼          ▼
     SUCCEEDED   RETRY_      recovery
                SCHEDULED       │
                   │            │
                   └──────┬─────┘
                          ▼
                       QUEUED

```
When retry attempts are exhausted:

```
RUNNING → DEAD
```
The Job state model also prevents invalid lifecycle transitions.
This makes state a first-class part of the system rather than an implicit consequence of queue membership.

### Queue Semantics & Priority

ForgeQueue maintains separate ready queues for:
```
HIGH
DEFAULT
LOW
```

Workers inspect these queues according to priority.
Queue membership and job state are deliberately treated as separate concepts. A queue entry can become stale—for example, after a job has already transitioned to a terminal state or has been recovered.
The claim logic therefore validates the job's current state rather than assuming that the presence of a job ID in a Redis list means the job is executable.
This allows stale queue entries to be discarded without preventing valid jobs behind them from being processed.

### Atomic Claiming & Leases
A worker cannot safely claim a job through a naïve sequence such as:
```
READ job state
     ↓
check QUEUED
     ↓
set RUNNING
```
Two workers could observe the same state before either writes the transition.
ForgeQueue instead performs the critical claim operation atomically through a Redis Lua script.
Conceptually:
```
RPOP ready queue
       │
       ▼
Is job still QUEUED?
       │
      yes
       │
       ├── create processing lease
       ├── generate execution token
       ├── mark job RUNNING
       └── return job
```
The processing lease is stored in a Redis sorted set with the lease expiration timestamp as its score.
This gives the recovery mechanism a way to identify executions whose ownership may have expired.

### Execution Ownership & Stale Workers
A logical job and an execution attempt are different concepts.

ForgeQueue therefore uses: 
```
job_id
execution_token
```
job_id identifies the logical job.

execution_token identifies the specific execution currently holding the job's ownership.

When a worker claims a job:
```
job_id = J

execution A
token = T1
```
If the lease expires and recovery returns the job to the queue:
```
execution A
T1
   │
   │ lease expires
   ▼
recovered
   │
   ▼
execution B
T2
```
The second execution receives a different token.

ACK and failure resolution require both the job_id and the current execution_token. The Redis-side operation verifies that:

- the job is still RUNNING, and
- the stored execution token matches the caller's token.

Only then can the execution transition the job.

Therefore:
```
Worker A (T1) ── stale ──X──> job
Worker B (T2) ── current ──✓──> job
```
This prevents a stale execution from acknowledging or resolving a newer execution.

The same ownership check is also used for lease renewal.

### Retries, Backoff & Dead-Letter Queue
When task execution fails, the worker calculates the next retry time using an exponential retry delay.

The failure transition is resolved atomically against the current execution token.

If retries remain:
```
RUNNING
   ↓
RETRY_SCHEDULED
   ↓
retry timestamp
   ↓
ready queue
```
If the retry limit has been exhausted:
```
RUNNING
   ↓
DEAD
   ↓
Dead-Letter Queue
```
This keeps retry scheduling separate from immediate queue execution while preserving the job's lifecycle state.

### Delayed & Cron Scheduling
ForgeQueue supports jobs that should not immediately enter a ready queue.

Delayed work is represented using timestamps and becomes eligible when its scheduled time is reached.

The scheduler moves due work into the appropriate ready queue.

Cron scheduling builds on the same idea for recurring execution: the scheduler maintains the schedule and enqueues the appropriate execution when a cron occurrence becomes due.

The scheduling logic also handles stale or invalid entries so that one malformed or obsolete scheduled entry does not prevent other valid work from being processed.

### Worker Execution & Graceful Shutdown
Workers retrieve jobs from the highest-priority available queue and resolve their execution through the task registry.

During execution, the worker periodically renews its lease:
```
claim
  │
  ├── execute task
  │
  ├── renew lease
  │
  ├── renew lease
  │
  └── ACK

```
Lease renewal is ownership-aware: a worker cannot renew a lease after its execution has lost ownership.

Workers also handle shutdown signals and stop taking new work while allowing the current worker lifecycle to terminate cleanly.

The worker pool uses multiprocessing to allow multiple worker processes to contend for jobs concurrently.

### Observability & Metrics
ForgeQueue maintains lightweight Redis-backed metrics.

Current metrics include:

- jobs processed
- jobs failed
- jobs retried
- jobs moved to the dead-letter queue
- cumulative execution time
- execution count
- current queue depth

Historical execution metrics and current queue state are intentionally separate concepts.
For example:
```
Historical:
jobs_processed
job_exec_time
job_exec_time_count

Current:
queue:high
queue:default
queue:low
queue:processing
queue:retry
queue:dead
```
This provides basic operational visibility without introducing a full external observability stack.
---

## Correctness & Failure Semantics

ForgeQueue explicitly tests several failure and concurrency boundaries.

```
| Scenario | Expected behavior |
|---|---|
| Two workers claim the same job | Only one execution succeeds in claiming it |
| Worker crashes while holding a lease | Expired execution becomes recoverable |
| Current worker renews lease | Lease is extended |
| Stale worker renews lease | Renewal is rejected |
| Stale worker ACKs recovered execution | ACK is rejected |
| Stale worker resolves recovered execution | Failure resolution is rejected |
| Two workers ACK the same execution | Only one ACK succeeds |
| Recovery runs concurrently | An execution is recovered at most once |
| Claim races with recovery | A fresh execution is not incorrectly recovered |
| Duplicate failure resolution | Only one resolution changes state |
| Stale queue entry encountered | Invalid entry does not hide valid work |
```
A key boundary is worth making explicit:
     **Execution ownership fencing is not the same as exactly-once external side effects.**

  The execution token prevents an obsolete worker from mutating ForgeQueue's state after ownership has moved to another execution. It cannot prevent an old task that continues running after lease loss from performing an external side effect outside ForgeQueue.

Applications using ForgeQueue therefore still need idempotent task behavior when external side effects matter.

## Verification & Testing

The test suite combines unit, integration, failure-recovery, and multi-process concurrency tests.

The current suite contains 43 tests, covering:

### Lifecycle & queue behavior
- job lifecycle transitions
- priority ordering
- stale queue entries
- scheduled jobs
- retries
- dead-letter handling

### Execution ownership
- lease creation
- lease expiration
- lease renewal
- stale worker ACK
- stale worker failure resolution
- lost ownership

### Concurrency
- concurrent claiming
- multi-worker contention
- concurrent ACK
- duplicate ACK
- concurrent recovery
- concurrent failure resolution
- claim/recovery races

### Worker behavior
- crash recovery
- worker lease renewal
- graceful shutdown
- execution metrics
- failure metrics

### Current verification result
```
43 passed in 86.36s
```
The full suite was executed with Python 3.13.5 and pytest 9.1.1 on Windows.

The test suite is intentionally biased toward state-transition and concurrency correctness, rather than only testing the happy path.

## ⚙️ Reproducibility
**Requirements**

- Python 3.10+
- Redis
- Docker (optional, for running Redis locally)

The package declares Redis, UUID6, and Croniter as its runtime dependencies.

### Installation

From the repository root:
```
pip install -e .
```
### Start Redis

Using Docker:
```
docker run -d -p 6379:6379 --name forgequeue-redis redis
```
### Run the test suite
```
pytest -v
```
### Run ForgeQueue
Start the worker pool:
```
python -m forgequeue.workers.pool
```
Start the delayed-job scheduler:
```
python -m forgequeue.scheduler.scheduler
```
Start the cron scheduler:
```
python -m forgequeue.scheduler.cron_scheduler
```
Then enqueue jobs using the example producer.

    The exact runtime commands and example workflow should be kept synchronized with the   current package entry points as the project evolves.**

## Example Usage
A minimal job consists of a task name and payload.

Conceptually:
```
from forgequeue.core.job import Job
from forgequeue.core.queue import enqueue

job = Job.create(
    task_name="print_message",
    payload={"message": "Hello from ForgeQueue"},
)

enqueue(job)
```
The worker then:
```
Job created
    ↓
QUEUED
    ↓
Worker claims job
    ↓
RUNNING
    ↓
Task executes
    ↓
ACK
    ↓
SUCCEEDED
```
For a failed execution, the same lifecycle can instead enter the retry scheduler or dead-letter queue depending on the retry count.

## Repository Structure
```
forgequeue-lib/
│
├── forgequeue/
│   ├── core/
│   │   ├── job.py
│   │   ├── queue.py
│   │   ├── retry.py
│   │   ├── task_registry.py
│   │   └── metrics.py
│   │
│   ├── workers/
│   │   ├── worker.py
│   │   └── pool.py
│   │
│   ├── scheduler/
│   │   ├── scheduler.py
│   │   ├── retry_scheduler.py
│   │   └── cron_scheduler.py
│   │
│   ├── tasks/
│   │   └── example.py
│   │
│   ├── redis_client.py
│   ├── main.py
│   └── register_cron_job.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── pyproject.toml
└── README.md

```
The most important implementation boundary is core/queue.py, where queue operations, leases, execution ownership, recovery, and atomic Redis scripts are implemented.

## Limitations & Design Boundaries
ForgeQueue is an intentionally scoped systems implementation rather than a production replacement for established distributed task-processing platforms.

Current boundaries include:

- No exactly-once external side-effect guarantee. Execution ownership protects ForgeQueue's state but cannot roll back external effects from a worker that continues executing after losing its lease.
- No job cancellation or execution timeout mechanism.
- No distributed Redis high-availability evaluation.
- No production-scale throughput benchmark has been established.
- Observability is intentionally lightweight and currently uses Redis-backed metrics rather than Prometheus/OpenTelemetry.
- Task results are not currently provided as a durable result-storage abstraction.

These limitations define the scope of the current implementation rather than hidden guarantees.

## Future Work
Potential extensions include:

- job execution timeouts and cancellation
- durable task-result storage
- controlled throughput and latency benchmarking
- distributed scheduler coordination
- Prometheus/OpenTelemetry integration
- Redis high-availability deployment and failure testing
- stronger idempotency mechanisms for externally visible task effects

These would extend the system's operational capabilities without changing the core execution-ownership model.

## Related Systems & References
ForgeQueue is a small implementation intended to study mechanisms that also appear in established background-processing systems such as:

- Celery
- Sidekiq
- BullMQ

The project does not attempt to reproduce their full feature sets. Instead, it implements a narrower set of queueing, scheduling, retry, lease, recovery, and concurrency mechanisms directly on top of Redis.

Relevant Redis primitives include:

- Redis Lists for ready queues
- Redis Sorted Sets for time-based scheduling and processing leases
- Redis Hashes for job state
- Redis Lua scripts for atomic multi-operation state transitions

## Limitations & Design Boundaries
ForgeQueue deliberately does not attempt to solve every problem associated with distributed task processing.

### No general job cancellation
There is currently no general-purpose cancellation protocol for already-running tasks.
### No arbitrary task timeout enforcement
A processing lease provides ownership expiry and recovery semantics, but it does not forcibly terminate arbitrary Python task code.
### No distributed Redis high-availability deployment
The project currently focuses on queue semantics rather than validating a Redis HA topology or failover deployment.
### Lightweight observability
Metrics are stored directly in Redis. There is no Prometheus, OpenTelemetry, tracing backend, or dedicated monitoring dashboard.
### No durable result backend
The queue tracks job state, but it is not designed as a general-purpose durable result-storage system.
### External side effects are not exactly-once
Execution tokens fence stale queue operations, but they cannot universally guarantee exactly-once behavior for external systems.
Applications performing external side effects may still need idempotency keys, transactional boundaries, or other application-level safeguards.
### Redis availability remains a coordination dependency
Queue state transitions, leases, acknowledgements, and recovery depend on Redis being available.
These limitations are intentional boundaries of the current project rather than hidden assumptions.

## Project Focus
```
┌─────────────────────────────────────────────────────────────┐
│                         ForgeQueue                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Queue Semantics          Failure Handling                  │
│       │                         │                           │
│       ▼                         ▼                           │
│  Atomic Claiming ────────► Lease Recovery                   │
│       │                         │                           │
│       ▼                         ▼                           │
│  Execution Tokens ───────► Stale Worker Fencing             │
│       │                         │                           │
│       └──────────────┬──────────┘                           │
│                      ▼                                      │
│               Concurrent Correctness                        │
│                      │                                      │
│                      ▼                                      │
│               Tested State Transitions                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**ForgeQueue is primarily an exploration of the correctness boundaries behind background job processing: who owns a job, what happens when that owner disappears, and how the system prevents stale executions from corrupting newer state.**