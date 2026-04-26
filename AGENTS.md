# AGENTS.md

Guidance for LLM agents working on this repository.

## Project Overview

This is a Python MCP server for Bootlin Elixir (`https://elixir.bootlin.com`). It exposes tools for source browsing and symbol lookup through MCP stdio.

Current tools:

- `ident_lookup`
- `autocomplete`
- `get_raw_source`
- `list_projects`
- `list_versions`

## Repository Layout

- `src/server.py`: MCP tool definitions and stdio entrypoint.
- `src/elixir_client.py`: HTTP client, validation, response parsing, and Bootlin-specific behavior.
- `src/models.py`: project exception types.
- `tests/test_elixir_client.py`: mocked/unit tests.
- `tests/test_mcp_live.py`: live MCP stdio test against Bootlin.
- `README.md`: user-facing setup and tool documentation.
- `pyproject.toml`: package metadata and dependencies.

Keep the flat `src/*` module layout. Do not introduce a package directory such as `src/mcp_elixir_bootlin/` unless explicitly requested.

## Development Commands

Use the project virtualenv when available:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q src tests
.venv/bin/python src/server.py
```

If dependencies are missing, install with:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install pytest
```

Avoid installing into the system Python environment.

## Testing Expectations

Before finishing code changes, run:

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest
```

The test suite includes live checks against `https://elixir.bootlin.com`. If the live test fails because Bootlin is unavailable, rate-limited, or protected by anti-bot handling, report that clearly and still run the mocked tests if possible.

## Bootlin Elixir Notes

Official JSON API coverage is limited:

- `GET /api/ident/{project}/{ident}?version=...&family=...`
- `GET /acp?q=...&p=...&f=...`

Other functionality is derived from the web UI:

- raw source uses `/{project}/{version}/source/{path}?raw=1`
- project and version listing parse HTML navigation

Bootlin may redirect `latest` to a concrete version. For raw source, preserve `raw=1` across redirects; otherwise Bootlin returns rendered HTML instead of raw file bytes.

Bootlin may also return an Anubis anti-bot HTML page. Keep anti-bot detection explicit and return clear errors instead of attempting to parse that page as JSON or source.

## Symbol Families

Use these family values in tool docs and validation:

- `A`: all symbols
- `B`: DT compatible
- `C`: C/CPP/ASM
- `D`: Devicetree
- `K`: Kconfig
- `M`: Makefiles

Default family must remain `A` unless the user explicitly asks to change it.

## Coding Guidelines

- Prefer small, direct changes.
- Keep validation centralized in `src/elixir_client.py`.
- Preserve structured MCP outputs (`dict[str, Any]`) from tools.
- Do not print to stdout from the MCP server; stdout is reserved for MCP stdio JSON-RPC.
- Raise project exceptions from the client and convert them to `ValueError` only at MCP tool boundaries.
- Keep line lengths reasonable and code readable; no formatter is currently configured.
- Do not add upper limits to `max_results` or `max_bytes`; validate only that positive limits are integers >= 1.
- Do not add backward compatibility shims unless explicitly needed.

## Live Behavior To Preserve

- `list_projects()` should fetch a stable source page (`/linux/latest/source`) rather than relying on `/` redirect chains.
- `list_versions(project)` should include concrete versions parsed from the version sidebar and report `latest_resolved` when available.
- `get_raw_source(project="linux", version="latest", path="README")` should return raw README text, not HTML.

## Git Safety

- Do not commit unless the user explicitly asks.
- Do not revert unrelated changes.
- Do not use destructive git commands unless explicitly approved.
