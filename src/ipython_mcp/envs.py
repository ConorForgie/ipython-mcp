"""Resolve env specifications to a Python interpreter path."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HOME_ENVS = Path.home() / "envs"


class EnvError(RuntimeError):
    """Raised when an env spec can't be resolved or is missing ipykernel."""


@dataclass(frozen=True)
class ResolvedEnv:
    label: str
    python: Path


def resolve_env(spec: str | None) -> ResolvedEnv:
    """Resolve an env spec to a usable Python interpreter.

    Rules:
      - None / empty       → the MCP server's own interpreter (label "default").
      - contains "/" or "~" → treated as a path; uses ``<path>/bin/python``.
      - otherwise           → bare name; uses ``~/envs/<name>/bin/python``.

    Verifies the interpreter exists and that ``ipykernel`` is importable
    inside it; raises :class:`EnvError` with an install hint otherwise.
    """
    if spec is None or spec == "":
        env = ResolvedEnv(label="default", python=Path(sys.executable).resolve())
    elif "/" in spec or spec.startswith("~"):
        base = Path(spec).expanduser().resolve()
        env = ResolvedEnv(label=str(base), python=base / "bin" / "python")
    else:
        base = (HOME_ENVS / spec).resolve()
        env = ResolvedEnv(label=spec, python=base / "bin" / "python")

    if not env.python.exists() or not os.access(env.python, os.X_OK):
        raise EnvError(
            f"python interpreter not found at {env.python} for env '{env.label}'"
        )

    _check_ipykernel(env)
    return env


def _check_ipykernel(env: ResolvedEnv) -> None:
    try:
        result = subprocess.run(
            [str(env.python), "-c", "import ipykernel"],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise EnvError(f"timed out probing ipykernel in env '{env.label}'") from exc

    if result.returncode != 0:
        raise EnvError(
            f"ipykernel not found in env '{env.label}' "
            f"(python: {env.python}). Install with: {_install_hint(env)}"
        )


def _install_hint(env: ResolvedEnv) -> str:
    env_root = env.python.parent.parent
    if (env_root / "conda-meta").exists():
        return f"mamba install -p {env_root} -c conda-forge ipykernel"
    return f"{env.python} -m pip install ipykernel"
