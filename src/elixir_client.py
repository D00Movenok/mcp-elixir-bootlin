from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urljoin, urlparse

import httpx

from models import (
    AntiBotChallengeError,
    HttpStatusError,
    InvalidInputError,
    NetworkError,
    NotFoundError,
    UnexpectedResponseError,
)

_PROJECT_VERSION_RE = re.compile(r"^[a-zA-Z0-9_.,:/-]+$")
_IDENT_RE = re.compile(r"^[A-Za-z0-9_,.+?#-]+$")
_SOURCE_PATH_RE = re.compile(r"^[A-Za-z0-9_/.,+-]+$")
_VALID_FAMILIES = {"A", "B", "C", "D", "K", "M"}
_DEFAULT_PROJECT = "linux"
_PROJECT_LATEST_HREF_RE = re.compile(r'href="/([^/"?#]+)/latest/source"', re.IGNORECASE)
_PROJECT_LATEST_VALUE_RE = re.compile(r'value="/([^/"?#]+)/latest/source"', re.IGNORECASE)


class ElixirClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        user_agent: str = "mcp-elixir-bootlin/0.1",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }
        if extra_headers:
            headers.update(extra_headers)

        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers=headers,
            follow_redirects=True,
        )

    @classmethod
    def from_env(cls) -> "ElixirClient":
        base_url = os.getenv("ELIXIR_BASE_URL", "https://elixir.bootlin.com")
        timeout_raw = os.getenv("ELIXIR_TIMEOUT_SECONDS", "30")
        user_agent = os.getenv("ELIXIR_USER_AGENT", "mcp-elixir-bootlin/0.1")

        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise InvalidInputError("ELIXIR_TIMEOUT_SECONDS must be a number") from exc

        extra_headers: dict[str, str] | None = None
        headers_raw = os.getenv("ELIXIR_HEADERS_JSON")
        if headers_raw:
            try:
                parsed = json.loads(headers_raw)
            except json.JSONDecodeError as exc:
                raise InvalidInputError("ELIXIR_HEADERS_JSON must be valid JSON") from exc

            if not isinstance(parsed, dict):
                raise InvalidInputError("ELIXIR_HEADERS_JSON must be a JSON object")

            extra_headers = {}
            for key, value in parsed.items():
                extra_headers[str(key)] = str(value)

        return cls(
            base_url,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            extra_headers=extra_headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ident_lookup(
        self,
        *,
        project: str,
        ident: str,
        version: str = "latest",
        family: str = "A",
        max_results: int = 50,
    ) -> dict[str, Any]:
        project = _validate_project(project)
        ident = _validate_ident(ident)
        version = _validate_version(version)
        family = _validate_family(family)
        max_results = _validate_positive_limit(max_results, "max_results")

        path = f"/api/ident/{quote(project, safe='')}/{quote(ident, safe='')}"
        payload = await self._request_json(
            path,
            params={"version": version, "family": family},
        )

        if not isinstance(payload, dict):
            raise UnexpectedResponseError("Unexpected /api/ident response type")

        definitions = _as_list(payload.get("definitions"))
        references = _as_list(payload.get("references"))
        documentations = _as_list(payload.get("documentations"))

        return {
            "project": project,
            "ident": ident,
            "version": version,
            "family": family,
            "definitions_count": len(definitions),
            "references_count": len(references),
            "documentations_count": len(documentations),
            "definitions": definitions[:max_results],
            "references": references[:max_results],
            "documentations": documentations[:max_results],
            "truncated": (
                len(definitions) > max_results
                or len(references) > max_results
                or len(documentations) > max_results
            ),
        }

    async def autocomplete(
        self,
        *,
        project: str,
        prefix: str,
        family: str = "A",
        max_results: int = 10,
    ) -> dict[str, Any]:
        project = _validate_project(project)
        prefix = _validate_ident(prefix)
        family = _validate_family(family)
        max_results = _validate_positive_limit(max_results, "max_results")

        payload = await self._request_json(
            "/acp",
            params={"q": prefix, "p": project, "f": family},
        )

        if not isinstance(payload, list):
            raise UnexpectedResponseError("Unexpected /acp response type")

        results = [str(item) for item in payload]
        return {
            "project": project,
            "prefix": prefix,
            "family": family,
            "count": len(results),
            "results": results[:max_results],
            "truncated": len(results) > max_results,
        }

    async def get_raw_source(
        self,
        *,
        project: str,
        version: str,
        path: str,
        max_bytes: int = 200000,
    ) -> dict[str, Any]:
        project = _validate_project(project)
        version = _validate_version(version)
        path = _validate_source_path(path)
        max_bytes = _validate_positive_limit(max_bytes, "max_bytes")

        raw_path = (
            f"/{quote(project, safe='')}/{quote(version, safe='')}"
            f"/source/{quote(path, safe='/')}"
        )
        response = await self._request_preserving_params(raw_path, params={"raw": "1"})

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            raise UnexpectedResponseError(
                "Expected raw file bytes but got HTML page. "
                "The requested path may point to a directory or rendered page."
            )

        content_bytes = response.content
        truncated = len(content_bytes) > max_bytes
        content_bytes = content_bytes[:max_bytes]
        content_text = content_bytes.decode("utf-8", errors="replace")

        return {
            "project": project,
            "version": version,
            "path": path,
            "content": content_text,
            "content_type": response.headers.get(
                "content-type",
                "application/octet-stream",
            ),
            "bytes_returned": len(content_bytes),
            "truncated": truncated,
        }

    async def list_projects(self) -> dict[str, Any]:
        response = await self._request(f"/{_DEFAULT_PROJECT}/latest/source", params={})

        projects = _extract_projects_from_html(response.text)
        if not projects:
            raise UnexpectedResponseError("Could not parse project list from Elixir page")

        default_project, _ = _extract_project_and_version_from_source_path(response.url.path)

        return {
            "count": len(projects),
            "projects": projects,
            "default_project": default_project or _DEFAULT_PROJECT,
        }

    async def list_versions(
        self,
        *,
        project: str,
        max_results: int = 10000,
    ) -> dict[str, Any]:
        project = _validate_project(project)
        max_results = _validate_positive_limit(max_results, "max_results")

        response = await self._request(
            f"/{quote(project, safe='')}/latest/source",
            params={},
        )

        versions = _extract_versions_from_html(response.text, project)
        if not versions:
            raise UnexpectedResponseError("Could not parse version list from Elixir page")

        _, latest_resolved = _extract_project_and_version_from_source_path(response.url.path)

        return {
            "project": project,
            "latest_alias": "latest",
            "latest_resolved": latest_resolved,
            "count": len(versions),
            "versions": versions[:max_results],
            "truncated": len(versions) > max_results,
        }

    async def _request_json(self, path: str, *, params: dict[str, str]) -> Any:
        response = await self._request(path, params=params)

        try:
            return response.json()
        except ValueError as exc:
            snippet = response.text[:300].replace("\n", " ")
            raise UnexpectedResponseError(
                f"Expected JSON response but got different content: {snippet}"
            ) from exc

    async def _request(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise NetworkError(f"HTTP request failed ({type(exc).__name__}): {exc}") from exc

        self._validate_response(response)
        return response

    async def _request_preserving_params(
        self,
        path: str,
        *,
        params: dict[str, str],
    ) -> httpx.Response:
        current_path = path
        current_params = dict(params)

        for _ in range(10):
            try:
                response = await self._client.get(
                    current_path,
                    params=current_params,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                raise NetworkError(f"HTTP request failed ({type(exc).__name__}): {exc}") from exc

            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise HttpStatusError(
                        response.status_code,
                        "Redirect response has no location header",
                    )

                absolute_location = urljoin(str(response.request.url), location)
                parsed = urlparse(absolute_location)
                current_path = parsed.path
                location_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
                location_params.update(params)
                current_params = location_params
                continue

            self._validate_response(response)
            return response

        raise HttpStatusError(310, "Too many redirects while fetching source")

    def _validate_response(self, response: httpx.Response) -> None:
        if response.status_code == 404:
            raise NotFoundError("Requested project or endpoint was not found")

        if response.status_code >= 400:
            raise HttpStatusError(
                response.status_code,
                f"Elixir API returned HTTP {response.status_code}",
            )

        if _looks_like_antibot_page(response):
            raise AntiBotChallengeError(
                "Bootlin anti-bot challenge detected. "
                "Set ELIXIR_BASE_URL to a self-hosted Elixir instance, or provide "
                "browser session headers/cookies via ELIXIR_HEADERS_JSON."
            )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _validate_project(value: str) -> str:
    value = value.strip()
    if value and _PROJECT_VERSION_RE.fullmatch(value):
        return value
    raise InvalidInputError("Invalid project format")


def _validate_version(value: str) -> str:
    value = value.strip()
    if value and _PROJECT_VERSION_RE.fullmatch(value):
        return value
    raise InvalidInputError("Invalid version format")


def _validate_ident(value: str) -> str:
    value = value.strip()
    if value and _IDENT_RE.fullmatch(value):
        return value
    raise InvalidInputError("Invalid identifier format")


def _validate_family(value: str) -> str:
    value = value.strip().upper()
    if value in _VALID_FAMILIES:
        return value
    raise InvalidInputError("Invalid family, expected one of " + ','.join(_VALID_FAMILIES))


def _validate_positive_limit(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidInputError(f"{name} must be an integer")
    if value < 1:
        raise InvalidInputError(f"{name} must be >= 1")
    return value


def _validate_source_path(value: str) -> str:
    value = value.strip()
    if value.startswith("/"):
        value = value[1:]
    if not value:
        raise InvalidInputError("path must not be empty")
    if "/../" in value or value.startswith("../") or value.endswith("/.."):
        raise InvalidInputError("path must not contain parent directory segments")
    if _SOURCE_PATH_RE.fullmatch(value):
        return value
    raise InvalidInputError("Invalid source path format")


def _looks_like_antibot_page(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text.lower()

    if "anubis" in text:
        return True
    if "making sure you're not a bot" in text:
        return True
    if "protected by anubis" in text:
        return True
    if "text/html" in content_type and "loading..." in text and "bot" in text:
        return True
    return False


def _extract_projects_from_html(html: str) -> list[str]:
    projects: list[str] = []

    for candidate in _PROJECT_LATEST_HREF_RE.findall(html):
        name = candidate.strip()
        if name and name not in projects:
            projects.append(name)

    for candidate in _PROJECT_LATEST_VALUE_RE.findall(html):
        name = candidate.strip()
        if name and name not in projects:
            projects.append(name)

    return projects


def _extract_versions_from_html(html: str, project: str) -> list[str]:
    versions: list[str] = []

    start = html.find('<ul class="versions">')
    if start != -1:
        stop = html.find('<div class="filter-results">', start)
        if stop != -1:
            html = html[start:stop]

    anchor_pattern = re.compile(
        rf'<a\s+href="/{re.escape(project)}/([^/"?#]+)/source"[^>]*>\s*([^<]+?)\s*</a>',
        re.IGNORECASE,
    )
    for match in anchor_pattern.finditer(html):
        label = match.group(2).strip()
        token = unquote(match.group(1).strip())
        version = label if label else token
        if version and version not in versions:
            versions.append(version)

    if versions:
        return versions

    token_pattern = re.compile(
        rf'href="/{re.escape(project)}/([^/"?#]+)/source"',
        re.IGNORECASE,
    )
    for token in token_pattern.findall(html):
        version = unquote(token.strip())
        if version and version not in versions:
            versions.append(version)

    return versions


def _extract_project_and_version_from_source_path(path: str) -> tuple[str | None, str | None]:
    match = re.match(r"^/([^/]+)/([^/]+)/source(?:/|$)", path)
    if not match:
        return None, None

    project = unquote(match.group(1))
    version = unquote(match.group(2))
    return project, version
