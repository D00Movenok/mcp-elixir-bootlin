from __future__ import annotations


class ElixirError(Exception):
    """Base exception for Elixir client errors."""


class InvalidInputError(ElixirError):
    """Raised when input does not match Elixir API constraints."""


class NotFoundError(ElixirError):
    """Raised when requested resource does not exist."""


class NetworkError(ElixirError):
    """Raised for network-level failures."""


class HttpStatusError(ElixirError):
    """Raised for unexpected HTTP status codes."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class UnexpectedResponseError(ElixirError):
    """Raised when response shape or content type is unexpected."""


class AntiBotChallengeError(ElixirError):
    """Raised when Bootlin blocks automated clients with an anti-bot page."""
