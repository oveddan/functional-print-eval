"""The task cap for run_python's code under bwrap. Enforcement is tested end to end in
tests/test_run_python.py (a fork bomb and a thread bomb); this checks the bookkeeping."""
import os
import threading

from pbe.runner import task_limit
from pbe.runner.task_limit import BWRAP_OWN_TASKS, TaskLimit


def own_threads():
    status = dict(line.split(":", 1) for line in open("/proc/self/status").read().splitlines() if ":" in line)
    return int(status["Threads"])


def test_tasks_owned_by_counts_threads():
    # other tests' processes start and end meanwhile, so compare with this process alone
    stop = threading.Event()
    threads = [threading.Thread(target=stop.wait) for _ in range(5)]
    for thread in threads:
        thread.start()
    try:
        assert own_threads() >= 6
        assert task_limit.tasks_owned_by(os.getuid()) >= own_threads()
    finally:
        stop.set()
        for thread in threads:
            thread.join()


def test_not_root_caps_with_rlimit_nproc_above_what_the_user_already_runs(monkeypatch):
    monkeypatch.setattr(task_limit, "running_as_root", lambda: False)
    monkeypatch.setattr(task_limit, "tasks_owned_by", lambda uid: 40)
    limit = TaskLimit("pbe-run-python-test", max_tasks=32)
    assert limit.cgroup is None and limit.nproc == 40 + 32 + BWRAP_OWN_TASKS


def test_root_without_a_pids_cgroup_is_a_problem(monkeypatch):
    monkeypatch.setattr(task_limit, "running_as_root", lambda: True)
    monkeypatch.setattr(task_limit, "_pids_hierarchy", lambda: None)
    assert "no writable pids cgroup" in task_limit.problem()
    monkeypatch.setattr(task_limit, "running_as_root", lambda: False)
    assert task_limit.problem() is None  # RLIMIT_NPROC needs nothing
