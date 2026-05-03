"""End-to-end smoke against the ipython-mcp server over stdio.

Runs via ``pixi run -e dev python tests/smoke.py``.
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _payload(result):
    """Pull the structured payload (or text) out of a CallToolResult.

    For tools with structured output (dict return type), the payload is in
    ``structuredContent``.  For unstructured tools (plain str return), the
    payload is the raw text content.
    """
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    if result.content and hasattr(result.content[0], "text"):
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

            # --- success: expression result ---
            result = await session.call_tool(
                "execute", {"session": "s1", "code": "x = 1 + 1\nx"}
            )
            r = _payload(result)
            print("execute(s1):", repr(r))
            assert not result.isError
            assert r == "2", f"expected '2', got {r!r}"

            # --- state survives across calls ---
            result = await session.call_tool(
                "execute", {"session": "s1", "code": "x"}
            )
            r = _payload(result)
            print("state survived:", repr(r))
            assert r == "2", f"expected '2', got {r!r}"

            # --- list sessions ---
            r = _payload(await session.call_tool("list_sessions", {}))
            print("list:", r)
            assert len(r) == 1 and r[0]["name"] == "s1"

            # --- env error ---
            result = await session.call_tool(
                "execute",
                {
                    "session": "bad",
                    "code": "1",
                    "env": "definitely-not-an-env-12345",
                },
            )
            print("env_error isError:", result.isError, "-", _payload(result)[:120])
            assert result.isError
            assert "definitely-not-an-env-12345" in _payload(result)

            # --- timeout ---
            result = await session.call_tool(
                "execute",
                {
                    "session": "loop",
                    "code": "import time\nfor i in range(20):\n    time.sleep(0.5)",
                    "timeout_s": 1.5,
                },
            )
            print("timeout isError:", result.isError)
            assert result.isError
            assert "Timeout" in _payload(result)

            # --- reset ---
            r = _payload(await session.call_tool("reset", {"session": "s1"}))
            assert r["ok"]

            # --- error: NameError after reset ---
            result = await session.call_tool(
                "execute", {"session": "s1", "code": "x"}
            )
            r = _payload(result)
            print("after reset isError:", result.isError, "-", r[-120:])
            assert result.isError
            assert "NameError" in r

            # --- shutdown and cleanup ---
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
