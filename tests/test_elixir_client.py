from __future__ import annotations

import asyncio

import httpx
import pytest

from elixir_client import ElixirClient
from models import (
    AntiBotChallengeError,
    HttpStatusError,
    InvalidInputError,
    NotFoundError,
    UnexpectedResponseError,
)


def _make_client(handler) -> ElixirClient:
    client = ElixirClient("https://example.test")
    old_client = client._client
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        headers={"Accept": "application/json", "User-Agent": "test-agent"},
    )
    asyncio.run(old_client.aclose())
    return client


def test_ident_lookup_success_with_truncation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/ident/linux/sched_clock"
        assert request.url.params["version"] == "latest"
        assert request.url.params["family"] == "A"
        return httpx.Response(
            200,
            json={
                "definitions": [{"path": "a", "line": 1}, {"path": "b", "line": 2}],
                "references": [{"path": "c", "line": 3}],
                "documentations": [{"path": "d", "line": 4}],
            },
        )

    client = _make_client(handler)
    try:
        result = asyncio.run(
            client.ident_lookup(
                project="linux",
                ident="sched_clock",
                version="latest",
                max_results=1,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result["definitions_count"] == 2
    assert result["references_count"] == 1
    assert result["documentations_count"] == 1
    assert len(result["definitions"]) == 1
    assert len(result["references"]) == 1
    assert len(result["documentations"]) == 1
    assert result["truncated"] is True


def test_autocomplete_success_with_truncation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/acp"
        assert request.url.params["q"] == "sched_c"
        assert request.url.params["p"] == "linux"
        assert request.url.params["f"] == "A"
        return httpx.Response(200, json=["sched_cache", "sched_clock"])

    client = _make_client(handler)
    try:
        result = asyncio.run(
            client.autocomplete(
                project="linux",
                prefix="sched_c",
                max_results=1,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result["count"] == 2
    assert result["results"] == ["sched_cache"]
    assert result["truncated"] is True


def test_404_maps_to_not_found_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = _make_client(handler)
    try:
        with pytest.raises(NotFoundError):
            asyncio.run(client.ident_lookup(project="linux", ident="foo"))
    finally:
        asyncio.run(client.aclose())


def test_500_maps_to_http_status_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    client = _make_client(handler)
    try:
        with pytest.raises(HttpStatusError) as exc_info:
            asyncio.run(client.autocomplete(project="linux", prefix="foo"))
    finally:
        asyncio.run(client.aclose())

    assert exc_info.value.status_code == 500


def test_antibot_page_detection() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="Making sure you're not a bot. Protected by Anubis",
            headers={"content-type": "text/html"},
        )

    client = _make_client(handler)
    try:
        with pytest.raises(AntiBotChallengeError):
            asyncio.run(client.ident_lookup(project="linux", ident="foo"))
    finally:
        asyncio.run(client.aclose())


def test_non_json_response_detection() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="plain text", headers={"content-type": "text/plain"})

    client = _make_client(handler)
    try:
        with pytest.raises(UnexpectedResponseError):
            asyncio.run(client.autocomplete(project="linux", prefix="foo"))
    finally:
        asyncio.run(client.aclose())


def test_input_validation_rejects_invalid_family() -> None:
    client = _make_client(lambda _: httpx.Response(200, json=[]))
    try:
        with pytest.raises(InvalidInputError):
            asyncio.run(client.autocomplete(project="linux", prefix="foo", family="X"))
    finally:
        asyncio.run(client.aclose())


def test_get_raw_source_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/linux/latest/source/include/linux/sched.h"
        assert request.url.params["raw"] == "1"
        return httpx.Response(
            200,
            content=b"line1\nline2\n",
            headers={"content-type": "application/octet-stream"},
        )

    client = _make_client(handler)
    try:
        result = asyncio.run(
            client.get_raw_source(
                project="linux",
                version="latest",
                path="include/linux/sched.h",
                max_bytes=100,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result["project"] == "linux"
    assert result["version"] == "latest"
    assert result["path"] == "include/linux/sched.h"
    assert result["content"] == "line1\nline2\n"
    assert result["truncated"] is False


def test_get_raw_source_truncates_content() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abcdef", headers={"content-type": "text/plain"})

    client = _make_client(handler)
    try:
        result = asyncio.run(
            client.get_raw_source(
                project="linux",
                version="latest",
                path="kernel/sched/core.c",
                max_bytes=3,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result["content"] == "abc"
    assert result["bytes_returned"] == 3
    assert result["truncated"] is True


def test_get_raw_source_rejects_invalid_path() -> None:
    client = _make_client(lambda _: httpx.Response(200, content=b""))
    try:
        with pytest.raises(InvalidInputError):
            asyncio.run(
                client.get_raw_source(
                    project="linux",
                    version="latest",
                    path="../etc/passwd",
                )
            )
    finally:
        asyncio.run(client.aclose())


def test_get_raw_source_preserves_raw_query_on_redirect() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.url.params.get("raw", "")))
        if request.url.path == "/linux/latest/source/README":
            return httpx.Response(302, headers={"location": "/linux/v7.0.1/source/README"})
        if request.url.path == "/linux/v7.0.1/source/README":
            assert request.url.params["raw"] == "1"
            return httpx.Response(200, content=b"hello\n", headers={"content-type": "text/plain"})
        return httpx.Response(500, text="unexpected path")

    client = _make_client(handler)
    try:
        result = asyncio.run(
            client.get_raw_source(
                project="linux",
                version="latest",
                path="README",
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert result["content"] == "hello\n"
    assert calls == [
        ("/linux/latest/source/README", "1"),
        ("/linux/v7.0.1/source/README", "1"),
    ]


def test_get_raw_source_rejects_html_page() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>page</html>", headers={"content-type": "text/html"})

    client = _make_client(handler)
    try:
        with pytest.raises(UnexpectedResponseError):
            asyncio.run(
                client.get_raw_source(
                    project="linux",
                    version="latest",
                    path="README",
                )
            )
    finally:
        asyncio.run(client.aclose())


def test_list_projects_parses_sidebar() -> None:
    html = """
    <select class=\"select-projects\">
      <option value=\"/linux/latest/source\">linux</option>
      <option value=\"/u-boot/latest/source\">u-boot</option>
    </select>
    <ul class=\"projects\">
      <li><a href=\"/linux/latest/source\">linux</a></li>
      <li><a href=\"/u-boot/latest/source\">u-boot</a></li>
    </ul>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    client = _make_client(handler)
    try:
        result = asyncio.run(client.list_projects())
    finally:
        asyncio.run(client.aclose())

    assert result["count"] == 2
    assert result["projects"] == ["linux", "u-boot"]


def test_list_versions_parses_version_menu() -> None:
    html = """
    <ul class=\"versions\">
      <li><a href=\"/linux/v7.0.1/source\">v7.0.1</a></li>
      <li><a href=\"/linux/v7.0/source\">v7.0</a></li>
      <li><a href=\"/linux/v7.0-rc7/source\">v7.0-rc7</a></li>
    </ul>
    <div class=\"filter-results\"></div>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    client = _make_client(handler)
    try:
        result = asyncio.run(client.list_versions(project="linux"))
    finally:
        asyncio.run(client.aclose())

    assert result["project"] == "linux"
    assert result["count"] == 3
    assert result["versions"] == ["v7.0.1", "v7.0", "v7.0-rc7"]


def test_list_versions_truncates() -> None:
    html = """
    <ul class=\"versions\">
      <li><a href=\"/linux/v3/source\">v3</a></li>
      <li><a href=\"/linux/v2/source\">v2</a></li>
      <li><a href=\"/linux/v1/source\">v1</a></li>
    </ul>
    <div class=\"filter-results\"></div>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    client = _make_client(handler)
    try:
        result = asyncio.run(client.list_versions(project="linux", max_results=2))
    finally:
        asyncio.run(client.aclose())

    assert result["count"] == 3
    assert result["versions"] == ["v3", "v2"]
    assert result["truncated"] is True


def test_positive_limits_have_no_upper_bound() -> None:
    html = """
    <ul class=\"versions\">
      <li><a href=\"/linux/v1/source\">v1</a></li>
    </ul>
    <div class=\"filter-results\"></div>
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    client = _make_client(handler)
    try:
        result = asyncio.run(client.list_versions(project="linux", max_results=30000))
    finally:
        asyncio.run(client.aclose())

    assert result["versions"] == ["v1"]
