import pytest

from forgequeue.core.job import Job, JobStatus


def test_successful_lifecycle():
    job = Job.create("test", {})

    job.transition_to(JobStatus.QUEUED)
    job.transition_to(JobStatus.RUNNING)
    job.transition_to(JobStatus.SUCCEEDED)

    assert job.status == JobStatus.SUCCEEDED


def test_retry_lifecycle():
    job = Job.create("test", {})

    job.transition_to(JobStatus.QUEUED)
    job.transition_to(JobStatus.RUNNING)
    job.transition_to(JobStatus.FAILED)
    job.transition_to(JobStatus.RETRY_SCHEDULED)
    job.transition_to(JobStatus.QUEUED)

    assert job.status == JobStatus.QUEUED


def test_dead_lifecycle():
    job = Job.create("test", {})

    job.transition_to(JobStatus.QUEUED)
    job.transition_to(JobStatus.RUNNING)
    job.transition_to(JobStatus.FAILED)
    job.transition_to(JobStatus.DEAD)

    assert job.status == JobStatus.DEAD


def test_invalid_transition():
    job = Job.create("test", {})

    with pytest.raises(ValueError):
        job.transition_to(JobStatus.SUCCEEDED)


def test_terminal_state_cannot_transition():
    job = Job.create("test", {})

    job.transition_to(JobStatus.QUEUED)
    job.transition_to(JobStatus.RUNNING)
    job.transition_to(JobStatus.SUCCEEDED)

    with pytest.raises(ValueError):
        job.transition_to(JobStatus.RUNNING)