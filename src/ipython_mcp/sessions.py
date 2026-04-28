"""Session manager: maps session names to long-lived kernels and serializes calls."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .envs import ResolvedEnv, resolve_env
from .kernel import ExecuteResult, Kernel


@dataclass
class ExecuteResponse:
    status: str
    stdout: str
    stderr: str
    result: str | None
    error: str | None
    execution_count: int | None
    warning: str | None = None


@dataclass
class SessionInfo:
    name: str
    env: str
    python: str
    status: str  # "idle" | "busy"
    uptime_s: float
    exec_count: int


@dataclass
class Session:
    name: str
    env: ResolvedEnv
    kernel: Kernel
    created_at: float = field(default_factory=time.monotonic)
    exec_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    busy: bool = False


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._dict_lock = threading.Lock()

    def execute(
        self,
        name: str,
        code: str,
        env_spec: str | None,
        timeout_s: float,
    ) -> ExecuteResponse:
        warning: str | None = None
        with self._dict_lock:
            session = self._sessions.get(name)
            if session is None:
                resolved = resolve_env(env_spec)
                kernel = Kernel()
                kernel.start(resolved.python)
                session = Session(name=name, env=resolved, kernel=kernel)
                self._sessions[name] = session
            elif env_spec is not None:
                requested = resolve_env(env_spec)
                if requested.python != session.env.python:
                    warning = (
                        f"session '{name}' is bound to env '{session.env.label}' "
                        f"({session.env.python}); ignoring requested env "
                        f"'{requested.label}'. Use shutdown('{name}') first to rebind."
                    )

        with session.lock:
            session.busy = True
            try:
                result = session.kernel.execute(code, timeout_s=timeout_s)
            finally:
                session.busy = False
            session.exec_count += 1

        return _to_response(result, warning)

    def list(self) -> list[SessionInfo]:
        with self._dict_lock:
            now = time.monotonic()
            return [
                SessionInfo(
                    name=s.name,
                    env=s.env.label,
                    python=str(s.env.python),
                    status="busy" if s.busy else "idle",
                    uptime_s=round(now - s.created_at, 2),
                    exec_count=s.exec_count,
                )
                for s in self._sessions.values()
            ]

    def reset(self, name: str) -> None:
        with self._dict_lock:
            session = self._sessions.get(name)
            if session is None:
                raise KeyError(f"unknown session '{name}'")
        with session.lock:
            session.kernel.shutdown()
            new_kernel = Kernel()
            new_kernel.start(session.env.python)
            session.kernel = new_kernel
            session.exec_count = 0
            session.created_at = time.monotonic()

    def shutdown(self, name: str) -> None:
        with self._dict_lock:
            session = self._sessions.pop(name, None)
        if session is None:
            raise KeyError(f"unknown session '{name}'")
        with session.lock:
            session.kernel.shutdown()

    def interrupt(self, name: str) -> None:
        with self._dict_lock:
            session = self._sessions.get(name)
        if session is None:
            raise KeyError(f"unknown session '{name}'")
        session.kernel.interrupt()

    def shutdown_all(self) -> None:
        with self._dict_lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for s in sessions:
            try:
                s.kernel.shutdown()
            except Exception:
                pass


def _to_response(result: ExecuteResult, warning: str | None) -> ExecuteResponse:
    return ExecuteResponse(
        status=result.status,
        stdout=result.stdout,
        stderr=result.stderr,
        result=result.result,
        error=result.error,
        execution_count=result.execution_count,
        warning=warning,
    )
