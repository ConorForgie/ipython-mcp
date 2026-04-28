"""Tests for SessionManager."""

from __future__ import annotations

import sys

import pytest

from ipython_mcp.sessions import SessionManager


@pytest.fixture
def manager():
    m = SessionManager()
    yield m
    m.shutdown_all()


def test_first_call_creates_session(manager):
    resp = manager.execute("s1", "x = 7\nx", env_spec=None, timeout_s=15)
    assert resp.status == "ok"
    assert resp.result == "7"
    assert resp.warning is None

    listing = manager.list()
    assert len(listing) == 1
    assert listing[0].name == "s1"
    assert listing[0].env == "default"


def test_state_persists_across_execute_calls(manager):
    manager.execute("s1", "y = 100", env_spec=None, timeout_s=15)
    resp = manager.execute("s1", "y * 2", env_spec=None, timeout_s=15)
    assert resp.result == "200"


def test_env_mismatch_warns_but_executes(manager, tmp_path):
    # Build a fake "other env" that points at the same python so we get a
    # different .python path from the first session's resolved one.
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").symlink_to(sys.executable)

    manager.execute("s1", "1", env_spec=None, timeout_s=15)
    resp = manager.execute("s1", "2", env_spec=str(tmp_path), timeout_s=15)
    assert resp.status == "ok"
    assert resp.result == "2"
    assert resp.warning is not None
    assert "ignoring requested env" in resp.warning


def test_reset_wipes_state(manager):
    manager.execute("s1", "z = 'hi'", env_spec=None, timeout_s=15)
    manager.reset("s1")
    resp = manager.execute("s1", "z", env_spec=None, timeout_s=15)
    assert resp.status == "error"
    assert "NameError" in (resp.error or "")


def test_reset_unknown_session_raises(manager):
    with pytest.raises(KeyError):
        manager.reset("nope")


def test_shutdown_removes_session(manager):
    manager.execute("s1", "1", env_spec=None, timeout_s=15)
    manager.shutdown("s1")
    assert manager.list() == []


def test_shutdown_unknown_session_raises(manager):
    with pytest.raises(KeyError):
        manager.shutdown("nope")


def test_list_reports_exec_count_and_env(manager):
    manager.execute("a", "1", env_spec=None, timeout_s=15)
    manager.execute("a", "2", env_spec=None, timeout_s=15)
    manager.execute("b", "3", env_spec=None, timeout_s=15)

    by_name = {s.name: s for s in manager.list()}
    assert by_name["a"].exec_count == 2
    assert by_name["b"].exec_count == 1
    assert by_name["a"].status == "idle"


def test_interrupt_unblocks_long_cell(manager):
    # Start a long-running execute in a background thread, then interrupt.
    import threading

    result = {}

    def runner():
        result["resp"] = manager.execute(
            "s1",
            "import time\nfor i in range(100):\n    time.sleep(0.5)",
            env_spec=None,
            timeout_s=30,
        )

    # Prime the session synchronously so the thread doesn't race kernel startup.
    manager.execute("s1", "1", env_spec=None, timeout_s=15)
    t = threading.Thread(target=runner)
    t.start()
    # Give the cell time to actually start running.
    import time as _time
    _time.sleep(2.0)
    manager.interrupt("s1")
    t.join(timeout=10)
    assert not t.is_alive()
    assert result["resp"].status == "error"
    assert "KeyboardInterrupt" in (result["resp"].error or "")


def test_shutdown_all_clears_sessions(manager):
    manager.execute("a", "1", env_spec=None, timeout_s=15)
    manager.execute("b", "2", env_spec=None, timeout_s=15)
    manager.shutdown_all()
    assert manager.list() == []
