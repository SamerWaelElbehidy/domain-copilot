from __future__ import annotations

import httpx

from application.ports.llm_provider import ProviderRejectedError, ProviderUnavailableError

# Statuses that mean "this provider cannot serve you right now" (rate limit,
# timeout, server fault, or a bad or revoked key), so another provider may.
_UNAVAILABLE_STATUSES = {401, 403, 408, 409, 425, 429}


def translate(exc: httpx.HTTPError, provider: str) -> Exception:
    """Maps transport and HTTP failures to the port's two error types. Only
    the provider name and status code are kept: never the URL query, the
    headers (which carry the API key) or the response body."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in _UNAVAILABLE_STATUSES or code >= 500:
            return ProviderUnavailableError(f"{provider}: HTTP {code}")
        return ProviderRejectedError(f"{provider}: HTTP {code}")
    return ProviderUnavailableError(f"{provider}: {type(exc).__name__}")
