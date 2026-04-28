"""FastMCP server exposing the IPython kernel session manager over stdio."""

from __future__ import annotations

import atexit
import os
from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import FastMCP

from .envs import EnvError
from .sessions import SessionManager

_MIN_TIMEOUT_S = 10
_FALLBACK_TIMEOUT_S = 58

mcp = FastMCP("ipython-mcp")
_manager = SessionManager()
atexit.register(_manager.shutdown_all)


def _default_timeout_s() -> float:
    raw = os.environ.get("MCP_TOOL_TIMEOUT")
    if not raw:
        return _FALLBACK_TIMEOUT_S
    try:
        ms = float(raw)
    except ValueError:
        return _FALLBACK_TIMEOUT_S
    return max(_MIN_TIMEOUT_S, ms / 1000.0 - 2.0)


@mcp.tool()
def execute(
    session: str,
    code: str,
    env: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run ``code`` inside the kernel for ``session``.

    Creates the session on first use. ``env`` selects the Python environment for
    new sessions: a bare name like ``"news-monitor"`` resolves to
    ``~/envs/<name>/bin/python``; anything containing ``/`` is treated as a path.
    On subsequent calls the session's existing env is used and a ``warning`` is
    returned if a different env was requested.

    Returns ``{ status, stdout, stderr, result, error, execution_count, warning }``.
    ``status`` is one of ``"ok"``, ``"error"``, ``"timeout"``, ``"env_error"``.
    """
    effective_timeout = timeout_s if timeout_s is not None else _default_timeout_s()
    try:
        response = _manager.execute(session, code, env, effective_timeout)
    except EnvError as exc:
        return {
            "status": "env_error",
            "stdout": "",
            "stderr": "",
            "result": None,
            "error": str(exc),
            "execution_count": None,
            "warning": None,
        }
    return asdict(response)


@mcp.tool()
def list_sessions() -> list[dict[str, Any]]:
    """List active sessions with their env, status, uptime, and execution count."""
    return [asdict(info) for info in _manager.list()]


@mcp.tool()
def reset(session: str) -> dict[str, Any]:
    """Restart the kernel for ``session`` (wipes state, keeps name and env)."""
    try:
        _manager.reset(session)
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@mcp.tool()
def shutdown(session: str) -> dict[str, Any]:
    """Kill the kernel for ``session`` and forget the session."""
    try:
        _manager.shutdown(session)
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


@mcp.tool()
def interrupt(session: str) -> dict[str, Any]:
    """Send an interrupt to a running cell in ``session``."""
    try:
        _manager.interrupt(session)
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
