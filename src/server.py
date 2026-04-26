from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from elixir_client import ElixirClient
from models import ElixirError

mcp = FastMCP("elixir-bootlin")


@mcp.tool()
async def ident_lookup(
    project: str,
    ident: str,
    version: str = "latest",
    family: str = "A",
    max_results: int = 50,
) -> dict[str, Any]:
    """Lookup identifier definitions/references/documentation in Elixir.

    Symbol families:
    - A: all symbols
    - B: DT compatible
    - C: C/CPP/ASM
    - D: Devicetree
    - K: Kconfig
    - M: Makefiles

    Args:
        project: Elixir project name, for example linux or u-boot.
        ident: Identifier to search for.
        version: Project version tag or latest/latest-rc.
        family: Symbol family: A, B, C, D, K, or M.
        max_results: Max items returned per section.
    """
    client = ElixirClient.from_env()
    try:
        return await client.ident_lookup(
            project=project,
            ident=ident,
            version=version,
            family=family,
            max_results=max_results,
        )
    except ElixirError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        await client.aclose()


@mcp.tool()
async def autocomplete(
    project: str,
    prefix: str,
    family: str = "A",
    max_results: int = 10,
) -> dict[str, Any]:
    """Autocomplete identifiers in Elixir.

    Symbol families:
    - A: all symbols
    - B: DT compatible
    - C: C/CPP/ASM
    - D: Devicetree
    - K: Kconfig
    - M: Makefiles

    Args:
        project: Elixir project name, for example linux or u-boot.
        prefix: Identifier prefix to complete.
        family: Symbol family: A, B, C, D, K, or M.
        max_results: Maximum number of results returned.
    """
    client = ElixirClient.from_env()
    try:
        return await client.autocomplete(
            project=project,
            prefix=prefix,
            family=family,
            max_results=max_results,
        )
    except ElixirError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        await client.aclose()


@mcp.tool()
async def get_raw_source(
    project: str,
    version: str,
    path: str,
    max_bytes: int = 200000,
) -> dict[str, Any]:
    """Fetch raw source file contents from Elixir source endpoint.

    This wraps: GET /{project}/{version}/source/{path}?raw=1

    Args:
        project: Elixir project name, for example linux or u-boot.
        version: Project version tag, latest, or latest-rc.
        path: Repository file path, for example include/linux/sched.h.
        max_bytes: Maximum bytes returned in content.
    """
    client = ElixirClient.from_env()
    try:
        return await client.get_raw_source(
            project=project,
            version=version,
            path=path,
            max_bytes=max_bytes,
        )
    except ElixirError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        await client.aclose()


@mcp.tool()
async def list_projects() -> dict[str, Any]:
    """List available projects from the Elixir instance."""
    client = ElixirClient.from_env()
    try:
        return await client.list_projects()
    except ElixirError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        await client.aclose()


@mcp.tool()
async def list_versions(project: str, max_results: int = 10000) -> dict[str, Any]:
    """List available versions for a project.

    Args:
        project: Elixir project name, for example linux or u-boot.
        max_results: Maximum number of version entries returned.
    """
    client = ElixirClient.from_env()
    try:
        return await client.list_versions(project=project, max_results=max_results)
    except ElixirError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        await client.aclose()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
