"""OAuth2 client-credentials token acquisition + the auth-descriptor resolve step.

``build_auth_headers`` (``remote.auth``) is a pure, synchronous header formatter.
The ``client-credentials`` auth mode needs an HTTP round-trip to a token endpoint,
so we keep that out of ``build_auth_headers`` and put it here:
``resolve_auth_descriptor`` runs *after* decryption and *before*
``build_auth_headers``. For every mode except ``client-credentials`` it is a
pass-through; for ``client-credentials`` it fetches (or reuses a cached) access
token and returns a derived plain-bearer descriptor.

Tokens are cached in-process only — keyed by (tokenUrl, clientId, scope, audience),
never including the secret, and never persisted.
"""

from __future__ import annotations

import threading
import time

import httpx
import structlog

log = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 30
# Refresh a cached token this many seconds before its stated expiry, so we never
# hand out a token that expires mid-flight.
_REFRESH_SKEW_SECONDS = 30
# Fallback lifetime when the token endpoint omits ``expires_in``.
_DEFAULT_EXPIRES_IN = 3600

_CacheKey = tuple[str, str, str, str]
_cache: dict[_CacheKey, tuple[str, float]] = {}
_cache_lock = threading.Lock()


class TokenFetchError(Exception):
    """The client-credentials token endpoint could not be reached or returned an
    unusable response (non-2xx, non-JSON, or missing ``access_token``)."""


def reset_token_cache() -> None:
    """Clear the entire in-process token cache (test hook; never needed in production)."""
    with _cache_lock:
        _cache.clear()


def invalidate_token(descriptor: dict) -> None:
    """Drop any cached token for this descriptor's key.

    Called when a registration's credential is rotated: the cache key excludes the
    secret, so a stale token would otherwise be served until expiry. No-op for
    non-client-credentials descriptors and when nothing is cached.
    """
    if descriptor.get("mode") != "client-credentials":
        return
    with _cache_lock:
        removed = _cache.pop(_cache_key(descriptor), None)
    if removed is not None:
        log.debug(
            "oauth.token_cache.invalidated",
            token_url=descriptor.get("tokenUrl", ""),
            client_id=descriptor.get("clientId", ""),
        )


def _cache_key(descriptor: dict) -> _CacheKey:
    return (
        descriptor.get("tokenUrl", ""),
        descriptor.get("clientId", ""),
        descriptor.get("scope", ""),
        descriptor.get("audience", ""),
    )


def fetch_client_credentials_token(
    descriptor: dict, *, client: httpx.Client, timeout: int
) -> tuple[str, int]:
    """POST the client-credentials grant; return ``(access_token, expires_in)``.

    ``descriptor`` must be DECRYPTED (``clientSecret`` in plaintext). Client id and
    secret travel in the ``application/x-www-form-urlencoded`` body. Raises
    ``TokenFetchError`` on any failure.
    """
    data = {
        "grant_type": "client_credentials",
        "client_id": descriptor.get("clientId", ""),
        "client_secret": descriptor.get("clientSecret", ""),
    }
    if descriptor.get("scope"):
        data["scope"] = descriptor["scope"]
    if descriptor.get("audience"):
        data["audience"] = descriptor["audience"]

    token_url = descriptor["tokenUrl"]
    client_id = descriptor.get("clientId", "")
    log.debug("oauth.token_fetch.start", token_url=token_url, client_id=client_id)
    try:
        response = client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=httpx.Timeout(timeout),
        )
    except httpx.HTTPError as exc:  # connect / DNS / TLS / timeout / protocol
        log.debug("oauth.token_fetch.unreachable", token_url=token_url, error=str(exc))
        raise TokenFetchError(f"token endpoint unreachable: {exc}") from exc

    if not 200 <= response.status_code < 300:
        log.debug("oauth.token_fetch.http_error", token_url=token_url, status_code=response.status_code)
        raise TokenFetchError(
            f"token endpoint returned HTTP {response.status_code}: {response.text[:200]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        log.debug("oauth.token_fetch.invalid_json", token_url=token_url)
        raise TokenFetchError("token endpoint response is not valid JSON") from exc

    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        log.debug("oauth.token_fetch.missing_token", token_url=token_url)
        raise TokenFetchError("token endpoint response missing 'access_token'")

    expires_in = body.get("expires_in")
    if not isinstance(expires_in, int) or expires_in <= 0:
        expires_in = _DEFAULT_EXPIRES_IN
    log.debug("oauth.token_fetch.ok", token_url=token_url, expires_in=expires_in)
    return token, expires_in


def _fetch(descriptor: dict, *, client: httpx.Client | None, timeout: int) -> tuple[str, int]:
    """Run one token exchange, creating a short-lived client if none was injected."""
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(timeout))
    try:
        return fetch_client_credentials_token(descriptor, client=client, timeout=timeout)
    finally:
        if owns_client:
            client.close()


def _get_cached_token(descriptor: dict, *, client: httpx.Client | None, timeout: int) -> str:
    key = _cache_key(descriptor)
    token_url = descriptor.get("tokenUrl", "")
    client_id = descriptor.get("clientId", "")

    cached = _cache.get(key)
    if cached and cached[1] - _REFRESH_SKEW_SECONDS > time.monotonic():
        log.debug("oauth.token_cache.hit", token_url=token_url, client_id=client_id)
        return cached[0]

    # Serialize concurrent first-fetches (the orchestrator dispatches rows in
    # parallel) so a fresh token is fetched once, not once per worker.
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[1] - _REFRESH_SKEW_SECONDS > time.monotonic():
            log.debug("oauth.token_cache.hit", token_url=token_url, client_id=client_id)
            return cached[0]
        log.debug("oauth.token_cache.miss", token_url=token_url, client_id=client_id)
        token, expires_in = _fetch(descriptor, client=client, timeout=timeout)
        _cache[key] = (token, time.monotonic() + expires_in)
        log.debug("oauth.token_cache.stored", token_url=token_url, expires_in=expires_in)
        return token


def resolve_auth_descriptor(
    descriptor: dict,
    *,
    client: httpx.Client | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    use_cache: bool = True,
) -> dict:
    """Resolve a DECRYPTED descriptor into one ``build_auth_headers`` can format.

    Pass-through for every mode except ``client-credentials``, which is exchanged
    for a derived ``{"mode": "bearer", "credential": <access_token>}``. Raises
    ``TokenFetchError`` if the token cannot be obtained.

    ``use_cache=False`` forces a fresh token exchange that neither reads nor writes
    the shared cache — used by "Test connection" so it always exercises the
    credential the registrant actually entered.
    """
    mode = descriptor.get("mode")
    if mode != "client-credentials":
        log.debug("oauth.resolve.passthrough", mode=mode)
        return descriptor
    log.debug(
        "oauth.resolve.client_credentials",
        token_url=descriptor.get("tokenUrl", ""),
        use_cache=use_cache,
    )
    if use_cache:
        token = _get_cached_token(descriptor, client=client, timeout=timeout)
    else:
        token, _ = _fetch(descriptor, client=client, timeout=timeout)
    log.debug("oauth.resolve.bearer_ready")
    return {"mode": "bearer", "credential": token}
