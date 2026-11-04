"""Exceptions raised by the Neural SDK."""
from typing import Optional


class NeuralError(Exception):
    """Base class for all SDK errors."""


class APIConnectionError(NeuralError):
    """The server could not be reached (network problem or timeout)."""


class APIStatusError(NeuralError):
    """The API returned a non-success status."""

    def __init__(self, message: str, status_code: int, code: Optional[str] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after

    def __str__(self):
        return f"{self.status_code} {self.code or 'error'}: {self.message}"


class InvalidRequestError(APIStatusError):
    """400: the request was malformed or violated a limit."""


class AuthenticationError(APIStatusError):
    """401: missing, invalid or revoked API key."""


class NotFoundError(APIStatusError):
    """404: for example an unknown model."""


class RateLimitError(APIStatusError):
    """429: per-minute or daily limit reached. See `retry_after` (seconds) when present."""


class ServerError(APIStatusError):
    """5xx: the server or the AI model is unavailable."""


def from_response(status: int, body, retry_after=None) -> APIStatusError:
    err = (body or {}).get("error") if isinstance(body, dict) else None
    message = (err or {}).get("message") or f"HTTP {status}"
    code = (err or {}).get("code")
    cls = {400: InvalidRequestError, 401: AuthenticationError, 404: NotFoundError, 429: RateLimitError}.get(status)
    if cls is None:
        cls = ServerError if status >= 500 else APIStatusError
    return cls(message, status, code, retry_after)
