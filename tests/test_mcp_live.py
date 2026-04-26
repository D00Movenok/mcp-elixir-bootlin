from __future__ import annotations

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _run_live_checks() -> None:
    params = StdioServerParameters(command=".venv/bin/python", args=["src/server.py"], env={})

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()
            assert init_result.serverInfo.name == "elixir-bootlin"

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "ident_lookup" in tool_names
            assert "autocomplete" in tool_names
            assert "get_raw_source" in tool_names
            assert "list_projects" in tool_names
            assert "list_versions" in tool_names

            projects_result = await session.call_tool("list_projects", {})
            projects_structured = projects_result.structuredContent
            assert isinstance(projects_structured, dict)
            assert isinstance(projects_structured.get("projects"), list)
            assert projects_structured.get("count", 0) > 0
            assert "linux" in projects_structured.get("projects", [])

            versions_result = await session.call_tool(
                "list_versions",
                {"project": "linux", "max_results": 20},
            )
            versions_structured = versions_result.structuredContent
            assert isinstance(versions_structured, dict)
            assert versions_structured.get("project") == "linux"
            assert isinstance(versions_structured.get("versions"), list)
            assert versions_structured.get("count", 0) > 0

            auto_result = await session.call_tool(
                "autocomplete",
                {"project": "linux", "prefix": "sched_c", "max_results": 5},
            )
            auto_structured = auto_result.structuredContent
            assert isinstance(auto_structured, dict)
            assert auto_structured.get("project") == "linux"
            assert auto_structured.get("prefix") == "sched_c"
            assert auto_structured.get("family") == "A"
            assert isinstance(auto_structured.get("results"), list)

            ident_result = await session.call_tool(
                "ident_lookup",
                {"project": "linux", "ident": "sched_clock", "version": "latest", "max_results": 5},
            )
            ident_structured = ident_result.structuredContent
            assert isinstance(ident_structured, dict)
            assert ident_structured.get("project") == "linux"
            assert ident_structured.get("ident") == "sched_clock"
            assert ident_structured.get("family") == "A"
            assert isinstance(ident_structured.get("definitions"), list)
            assert isinstance(ident_structured.get("references"), list)

            raw_result = await session.call_tool(
                "get_raw_source",
                {"project": "linux", "version": "latest", "path": "README"},
            )
            raw_structured = raw_result.structuredContent
            assert isinstance(raw_structured, dict)
            assert raw_structured.get("project") == "linux"
            assert raw_structured.get("version") == "latest"
            assert raw_structured.get("path") == "README"
            assert isinstance(raw_structured.get("content"), str)
            assert raw_structured.get("bytes_returned", 0) > 0


def test_mcp_live_end_to_end() -> None:
    asyncio.run(_run_live_checks())
