"""Integration tests for ipython_mcp.kernel.Kernel against a real ipykernel."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from ipython_mcp.kernel import Kernel

PYTHON = Path(sys.executable)


@pytest.fixture
def kernel():
    k = Kernel()
    k.start(PYTHON)
    yield k
    k.shutdown()


def test_simple_expression_returns_result(kernel):
    res = kernel.execute("1 + 1", timeout_s=15)
    assert res.status == "ok"
    assert res.result == "2"
    assert res.error is None
    assert res.execution_count == 1


def test_state_persists_across_calls(kernel):
    kernel.execute("x = 41", timeout_s=15)
    res = kernel.execute("x + 1", timeout_s=15)
    assert res.status == "ok"
    assert res.result == "42"


def test_stdout_captured(kernel):
    res = kernel.execute("print('hello'); print('world')", timeout_s=15)
    assert res.status == "ok"
    assert "hello" in res.stdout
    assert "world" in res.stdout
    assert res.result is None


def test_stderr_captured(kernel):
    code = "import sys; sys.stderr.write('boom\\n')"
    res = kernel.execute(code, timeout_s=15)
    assert res.status == "ok"
    assert "boom" in res.stderr


def test_error_includes_traceback(kernel):
    res = kernel.execute("1/0", timeout_s=15)
    assert res.status == "error"
    assert res.error is not None
    assert "ZeroDivisionError" in res.error


def test_timeout_returns_partial_and_keeps_kernel_alive(kernel):
    code = "import time\nfor i in range(20):\n    print(i, flush=True)\n    time.sleep(0.5)"
    start = time.monotonic()
    res = kernel.execute(code, timeout_s=1.5)
    elapsed = time.monotonic() - start
    assert res.status == "timeout"
    assert elapsed < 6  # interrupt + grace
    assert kernel.is_alive()
    follow = kernel.execute("'still here'", timeout_s=15)
    assert follow.status == "ok"
    assert follow.result == "'still here'"


def test_execution_count_increments(kernel):
    a = kernel.execute("1", timeout_s=15)
    b = kernel.execute("2", timeout_s=15)
    assert a.execution_count is not None
    assert b.execution_count is not None
    assert b.execution_count > a.execution_count


def test_shutdown_idempotent(kernel):
    kernel.shutdown()
    kernel.shutdown()
    assert not kernel.is_alive()
