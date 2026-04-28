"""Tests for ipython_mcp.envs.resolve_env."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ipython_mcp.envs import EnvError, resolve_env


def test_default_returns_server_python():
    env = resolve_env(None)
    assert env.label == "default"
    assert env.python == Path(sys.executable).resolve()


def test_empty_string_treated_as_default():
    env = resolve_env("")
    assert env.label == "default"


def test_path_resolution_uses_bin_python(tmp_path):
    # Build a fake env layout pointing python at the real interpreter so
    # the ipykernel probe (which the dev env satisfies) succeeds.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)

    env = resolve_env(str(tmp_path))
    assert env.python == tmp_path.resolve() / "bin" / "python"
    assert env.label == str(tmp_path.resolve())


def test_bare_name_resolves_under_home_envs(tmp_path, monkeypatch):
    fake_home_envs = tmp_path / "envs"
    fake_env = fake_home_envs / "myenv"
    (fake_env / "bin").mkdir(parents=True)
    (fake_env / "bin" / "python").symlink_to(sys.executable)

    monkeypatch.setattr("ipython_mcp.envs.HOME_ENVS", fake_home_envs)
    env = resolve_env("myenv")
    assert env.label == "myenv"
    assert env.python.name == "python"
    assert env.python.parent.parent == fake_env.resolve()


def test_missing_python_raises():
    with pytest.raises(EnvError, match="python interpreter not found"):
        resolve_env("/nonexistent/env-path-12345")


def test_missing_ipykernel_raises_with_install_hint(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)

    failing = subprocess.CompletedProcess(
        args=[], returncode=1, stdout=b"", stderr=b"ModuleNotFoundError: ipykernel",
    )
    with patch("ipython_mcp.envs.subprocess.run", return_value=failing):
        with pytest.raises(EnvError) as exc:
            resolve_env(str(tmp_path))
    assert "ipykernel not found" in str(exc.value)
    assert "Install with:" in str(exc.value)


def test_install_hint_for_conda_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)
    (tmp_path / "conda-meta").mkdir()  # marker for conda-style env

    failing = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"")
    with patch("ipython_mcp.envs.subprocess.run", return_value=failing):
        with pytest.raises(EnvError, match="mamba install"):
            resolve_env(str(tmp_path))
