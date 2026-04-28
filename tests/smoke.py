"""End-to-end smoke against the ipython-mcp server over stdio.

Runs via ``pixi run -e dev python tests/smoke.py``.
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _payload(result):
    """Pull the structured payload (or text) out of a CallToolResult.

    FastMCP wraps non-object returns as ``{"result": <value>}`` in
    ``structuredContent`` (since structured content must be an object); unwrap
    that so callers see the raw value.
    """
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    if result.content and hasattr(result.content[0], "text"):
        try:
            return json.loads(result.content[0].text)
        except json.JSONDecodeError:
            return result.content[0].text
    return None


async def main() -> int:
    params = StdioServerParameters(command="pixi", args=["run", "server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = sorted(t.name for t in tools.tools)
            print("tools:", tool_names)
            assert tool_names == [
                "execute",
                "interrupt",
                "list_sessions",
                "reset",
                "shutdown",
            ], tool_names

            r = _payload(
                await session.call_tool(
                    "execute", {"session": "s1", "code": "x = 1 + 1\nx"}
                )
            )
            print("execute(s1):", r)
            assert r["status"] == "ok"
            assert r["result"] == "2"

            r = _payload(
                await session.call_tool(
                    "execute", {"session": "s1", "code": "x"}
                )
            )
            print("state survived:", r["result"])
            assert r["result"] == "2"

            r = _payload(await session.call_tool("list_sessions", {}))
            print("list:", r)
            assert len(r) == 1 and r[0]["name"] == "s1"

            r = _payload(
                await session.call_tool(
                    "execute",
                    {
                        "session": "bad",
                        "code": "1",
                        "env": "definitely-not-an-env-12345",
                    },
                )
            )
            print("env_error:", r["status"], "-", r["error"][:120])
            assert r["status"] == "env_error"

            r = _payload(
                await session.call_tool(
                    "execute",
                    {
                        "session": "loop",
                        "code": "import time\nfor i in range(20):\n    time.sleep(0.5)",
                        "timeout_s": 1.5,
                    },
                )
            )
            print("timeout:", r["status"])
            assert r["status"] == "timeout"

            r = _payload(await session.call_tool("reset", {"session": "s1"}))
            assert r["ok"]
            r = _payload(
                await session.call_tool(
                    "execute", {"session": "s1", "code": "x"}
                )
            )
            print("after reset:", r["status"], "-", (r["error"] or "")[-40:])
            assert r["status"] == "error" and "NameError" in r["error"]

            r = _payload(await session.call_tool("shutdown", {"session": "s1"}))
            assert r["ok"]
            r = _payload(await session.call_tool("shutdown", {"session": "loop"}))
            assert r["ok"]
            r = _payload(await session.call_tool("list_sessions", {}))
            print("final list:", r)
            assert r == []

    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
