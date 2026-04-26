# MCP server for [elixir.bootlin.com](https://elixir.bootlin.com/)

MCP server exposing Bootlin Elixir lookup tools.

> ⚠️ Be careful, completely vibe-coded ⚠️
>
> (but manually verified)

## Tools

- `ident_lookup(project, ident, version="latest", family="A", max_results=50)`
  - Calls Elixir `GET /api/ident/{project}/{ident}`.
  - Returns definitions, references, and documentations with counts.
- `autocomplete(project, prefix, family="A", max_results=10)`
  - Calls Elixir `GET /acp`.
  - Returns identifier completions.
- `get_raw_source(project, version, path, max_bytes=200000)`
  - Calls Elixir `GET /{project}/{version}/source/{path}?raw=1`.
  - Returns raw file content.
- `list_projects()`
  - Lists available projects from the current Elixir instance.
- `list_versions(project, max_results=10000)`
  - Lists available versions for a specific project.

## Install

With pipx (recommended):

```bash
pipx install git+https://github.com/D00Movenok/mcp-elixir-bootlin.git
```

With uv:

```bash
uv pip install git+https://github.com/D00Movenok/mcp-elixir-bootlin.git
```

Or with a virtualenv:

```bash
git clone https://github.com/D00Movenok/mcp-elixir-bootlin.git
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

Environment variables:

- `ELIXIR_BASE_URL` (default: `https://elixir.bootlin.com`)
- `ELIXIR_TIMEOUT_SECONDS` (default: `30`)
- `ELIXIR_USER_AGENT` (default: `mcp-elixir-bootlin/0.1`)
- `ELIXIR_HEADERS_JSON` (optional JSON object with extra headers, for cookies/session)

## Claude Desktop MCP config example

```json
{
  "mcpServers": {
    "elixir": {
      "command": "mcp-elixir-bootlin",
      "env": {
        "ELIXIR_BASE_URL": "https://elixir.bootlin.com"
      }
    }
  }
}
```

## Important note about elixir.bootlin.com

`elixir.bootlin.com` is currently protected by Anubis anti-bot challenge for non-browser clients.

This server detects that response and returns a clear error instead of malformed JSON. If you hit this:

- point `ELIXIR_BASE_URL` to a self-hosted Elixir instance, or
- provide browser session headers/cookies through `ELIXIR_HEADERS_JSON`.
