"""Tests for KismetServiceManager start/restart preparation (service_manager.py).

subprocess.run is replaced by a recorder, so no systemctl or pkill is executed.
"""

import subprocess

import pytest

import service_manager


class FakeRun:
    """Stand-in for subprocess.run that records argv lists and returns success."""

    def __init__(self):
        self.calls = []
        self.fail_actions = set()

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        code = 1 if any(a in cmd for a in self.fail_actions) else 0
        return subprocess.CompletedProcess(cmd, code, stdout="kismet.service enabled", stderr="")

    def index_of(self, *prefix):
        prefix = list(prefix)
        for i, call in enumerate(self.calls):
            if call[: len(prefix)] == prefix:
                return i
        raise AssertionError(f"{prefix} was not run; calls were {self.calls}")


@pytest.fixture
def manager(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(service_manager.subprocess, "run", fake)
    monkeypatch.setattr(service_manager.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        service_manager.KismetServiceManager, "_find_systemctl", lambda self: "/usr/bin/systemctl"
    )
    monkeypatch.setattr(service_manager.time, "sleep", lambda seconds: None)
    mgr = service_manager.KismetServiceManager()
    fake.calls.clear()  # drop the probes made by __init__
    return mgr, fake


def test_start_kills_orphans_and_clears_failed_state_before_starting(manager):
    mgr, fake = manager

    assert mgr.start()["success"] is True

    kill = fake.index_of("pkill", "-f", "rtl_433")
    reset = fake.index_of("/usr/bin/systemctl", "reset-failed", "kismet")
    start = fake.index_of("/usr/bin/systemctl", "start", "kismet")
    assert kill < reset < start
    assert fake.calls[-1] == ["/usr/bin/systemctl", "start", "kismet"]


def test_restart_stops_then_prepares_then_starts(manager):
    mgr, fake = manager

    assert mgr.restart()["success"] is True

    stop = fake.index_of("/usr/bin/systemctl", "stop", "kismet")
    kill = fake.index_of("pkill", "-f", "rtl_433")
    reset = fake.index_of("/usr/bin/systemctl", "reset-failed", "kismet")
    start = fake.index_of("/usr/bin/systemctl", "start", "kismet")
    assert stop < kill < reset < start


def test_start_still_starts_when_reset_failed_errors(manager):
    mgr, fake = manager
    fake.fail_actions = {"reset-failed"}

    assert mgr.start()["success"] is True

    fake.index_of("/usr/bin/systemctl", "reset-failed", "kismet")
    assert fake.calls[-1] == ["/usr/bin/systemctl", "start", "kismet"]
