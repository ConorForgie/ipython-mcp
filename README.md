# ipython-mcp

An MCP server that gives Claude (or any MCP client) a stateful IPython kernel
per session, with optional per-environment isolation.

Each session is a long-lived `ipykernel` subprocess. Variables, imports, and
working directory persist across `execute` calls so Claude can iterate like a
notebook. Different sessions can run in different Python environments — point a
session at `~/envs/news-monitor`, another at an absolute path, and they coexist
in independent processes.

## Install

Requires [pixi](https://pixi.sh).

```bash
git clone <this repo> ~/code/ipython-mcp
cd ~/code/ipython-mcp
pixi install -e dev
pixi run -e dev test     # 25 tests
```

## Run

```bash
pixi run server
```

This launches `ipython-mcp` over stdio. Wire it into Claude Code via
`~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "ipython": {
      "command": "pixi",
      "args": ["run", "--manifest-path", "/home/you/code/ipython-mcp/pyproject.toml", "server"]
    }
  }
}
```

## Tools

| Tool | Args | Description |
|---|---|---|
| `execute` | `session`, `code`, `env=None`, `timeout_s=None` | Run code in `session`. Creates the kernel on first use. Returns `{ status, stdout, stderr, result, error, execution_count, warning }`. |
| `list_sessions` | — | All active sessions: `{ name, env, python, status, uptime_s, exec_count }`. |
| `reset` | `session` | Restart the kernel (wipes state, keeps name + env). |
| `shutdown` | `session` | Kill the kernel and forget the session. |
| `interrupt` | `session` | Send an interrupt to a running cell. |

### `execute` status values

- `ok` — clean run.
- `error` — cell raised; `error` contains the traceback.
- `timeout` — cell exceeded `timeout_s`; the kernel was interrupted, partial
  stdout/stderr are returned, and the session is still alive.
- `env_error` — env couldn't be resolved (missing interpreter or `ipykernel`).
  The `error` field includes an install hint.

## Environment resolution

The `env` argument follows two rules:

| `env` value | Resolves to |
|---|---|
| `None` (default) | the MCP server's own Python interpreter |
| bare name like `"news-monitor"` | `~/envs/<name>/bin/python` |
| anything containing `/` or `~` | `<expanded path>/bin/python` |

`env` is honored only when *creating* a session. On subsequent `execute` calls
the session keeps its original env; if a different `env` is requested, the
response includes a `warning` (the call still runs in the original env).

### `ipykernel` requirement

The target env must have `ipykernel` importable. If it doesn't, `execute`
returns `status: "env_error"` with an install hint, e.g.:

```
ipykernel not found in env 'news-monitor'
(python: /home/you/envs/news-monitor/bin/python).
Install with: mamba install -p /home/you/envs/news-monitor -c conda-forge ipykernel
```

The MCP server itself does not need `ipykernel` — only the target envs do.

## Timeouts

`timeout_s` defaults to `MCP_TOOL_TIMEOUT / 1000 - 2` seconds (or 58s if the
env var isn't set), so the kernel is interrupted and partial output is returned
*before* the MCP transport itself times out the call. Pass `timeout_s` to
override per-call.

## Layout

```
src/ipython_mcp/
├── server.py     # FastMCP tools + entry point
├── sessions.py   # SessionManager + per-session locking
├── kernel.py     # jupyter_client wrapper
└── envs.py       # env spec → python interpreter
```

## Roadmap

- [#1] Multimodal output: surface `image/png` outputs (matplotlib, etc.) as
  MCP image content blocks.
- Optional `auto_install_ipykernel` flag.
