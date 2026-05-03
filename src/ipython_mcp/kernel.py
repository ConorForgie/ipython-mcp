"""Thin wrapper around ``jupyter_client.KernelManager`` for one IPython kernel."""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from pathlib import Path

from jupyter_client.kernelspec import KernelSpec
from jupyter_client.manager import KernelManager

KERNEL_READY_TIMEOUT_S = 30
INTERRUPT_GRACE_S = 2


@dataclass
class ExecuteResult:
    status: str  # "ok" | "error" | "timeout"
    stdout: str
    stderr: str
    result: str | None
    error: str | None
    execution_count: int | None


class Kernel:
    def __init__(self) -> None:
        self.km: KernelManager | None = None
        self.kc = None

    def start(self, python_path: Path) -> None:
        km = KernelManager()
        spec = KernelSpec()
        spec.argv = [
            str(python_path),
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        spec.display_name = "custom"
        spec.language = "python"
        km._kernel_spec = spec
        km.start_kernel()
        kc = km.client()
        kc.start_channels()
        kc.wait_for_ready(timeout=KERNEL_READY_TIMEOUT_S)
        self.km = km
        self.kc = kc

    def execute(self, code: str, timeout_s: float) -> ExecuteResult:
        if self.kc is None or self.km is None:
            raise RuntimeError("kernel not started")

        msg_id = self.kc.execute(code, allow_stdin=False)
        deadline = time.monotonic() + timeout_s

        stdout: list[str] = []
        stderr: list[str] = []
        result: str | None = None
        error: str | None = None
        execution_count: int | None = None
        timed_out = False

        idle_seen = False
        while not idle_seen:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                self.km.interrupt_kernel()
                idle_seen = self._drain_after_interrupt(msg_id, stdout, stderr)
                break

            try:
                msg = self.kc.get_iopub_msg(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue

            if msg["parent_header"].get("msg_id") != msg_id:
                continue

            mtype = msg["msg_type"]
            content = msg["content"]
            if mtype == "stream":
                target = stdout if content.get("name") == "stdout" else stderr
                target.append(content.get("text", ""))
            elif mtype == "execute_result":
                result = content.get("data", {}).get("text/plain", result)
                execution_count = content.get("execution_count", execution_count)
            elif mtype == "display_data":
                if result is None:
                    result = content.get("data", {}).get("text/plain")
            elif mtype == "error":
                tb = content.get("traceback", [])
                error = "\n".join(tb) if tb else (
                    f"{content.get('ename')}: {content.get('evalue')}"
                )
            elif mtype == "execute_input":
                execution_count = content.get("execution_count", execution_count)
            elif mtype == "status" and content.get("execution_state") == "idle":
                idle_seen = True

        try:
            reply = self.kc.get_shell_msg(timeout=2)
            if reply["parent_header"].get("msg_id") == msg_id:
                execution_count = reply["content"].get(
                    "execution_count", execution_count
                )
        except queue.Empty:
            pass

        if timed_out:
            status = "timeout"
        elif error is not None:
            status = "error"
        else:
            status = "ok"

        return ExecuteResult(
            status=status,
            stdout="".join(stdout),
            stderr="".join(stderr),
            result=result,
            error=error,
            execution_count=execution_count,
        )

    def _drain_after_interrupt(
        self,
        msg_id: str,
        stdout: list[str],
        stderr: list[str],
    ) -> bool:
        kc = self.kc
        assert kc is not None
        deadline = time.monotonic() + INTERRUPT_GRACE_S
        idle_seen = False
        while time.monotonic() < deadline:
            try:
                msg = kc.get_iopub_msg(
                    timeout=max(0.05, deadline - time.monotonic())
                )
            except queue.Empty:
                break
            if msg["parent_header"].get("msg_id") != msg_id:
                continue
            mtype = msg["msg_type"]
            content = msg["content"]
            if mtype == "stream":
                target = stdout if content.get("name") == "stdout" else stderr
                target.append(content.get("text", ""))
            elif mtype == "status" and content.get("execution_state") == "idle":
                idle_seen = True
                break
        return idle_seen

    def interrupt(self) -> None:
        if self.km is not None:
            self.km.interrupt_kernel()

    def is_alive(self) -> bool:
        return self.km is not None and self.km.is_alive()

    def shutdown(self) -> None:
        if self.kc is not None:
            try:
                self.kc.stop_channels()
            except Exception:
                pass
            self.kc = None
        if self.km is not None:
            try:
                self.km.shutdown_kernel(now=False)
            except Exception:
                try:
                    self.km.shutdown_kernel(now=True)
                except Exception:
                    pass
            self.km = None
