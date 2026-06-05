"""OAuth2 client-credentials token fetch + resolve_auth_descriptor tests.

Driven by httpx.MockTransport — no socket. Covers the token exchange, failure
mapping to TokenFetchError, the in-process cache (hit + expiry refetch), and the
pass-through / bearer-derivation contract of resolve_auth_descriptor.
"""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from harness.remote import oauth
from harness.remote.oauth import (
    TokenFetchError,
    fetch_client_credentials_token,
    invalidate_token,
    resolve_auth_descriptor,
)

_CC = {
    "mode": "client-credentials",
    "tokenUrl": "https://idp.test/token",
    "clientId": "cid",
    "clientSecret": "secret",
}


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    oauth.reset_token_cache()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"access_token": "AT", "token_type": "Bearer", "expires_in": 3600}
    )


# --------------------------------------------------------------- fetch
def test_fetch_returns_token_and_expiry() -> None:
    token, expires_in = fetch_client_credentials_token(
        _CC, client=_client(_token_response), timeout=10
    )
    assert token == "AT"
    assert expires_in == 3600


def test_fetch_sends_grant_and_credentials_in_body() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["ctype"] = request.headers.get("Content-Type")
        captured["form"] = parse_qs(request.content.decode())
        return _token_response(request)

    descriptor = {**_CC, "scope": "a b", "audience": "aud"}
    fetch_client_credentials_token(descriptor, client=_client(h), timeout=10)

    assert captured["url"] == "https://idp.test/token"
    assert captured["ctype"] == "application/x-www-form-urlencoded"
    assert captured["form"] == {
        "grant_type": ["client_credentials"],
        "client_id": ["cid"],
        "client_secret": ["secret"],
        "scope": ["a b"],
        "audience": ["aud"],
    }


def test_fetch_omits_scope_and_audience_when_absent() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["form"] = parse_qs(request.content.decode())
        return _token_response(request)

    fetch_client_credentials_token(_CC, client=_client(h), timeout=10)
    assert "scope" not in captured["form"]
    assert "audience" not in captured["form"]


def test_fetch_defaults_expiry_when_missing() -> None:
    _, expires_in = fetch_client_credentials_token(
        _CC, client=_client(lambda r: httpx.Response(200, json={"access_token": "AT"})), timeout=10
    )
    assert expires_in == oauth._DEFAULT_EXPIRES_IN


# --------------------------------------------------------------- fetch failures
def test_non_2xx_raises() -> None:
    with pytest.raises(TokenFetchError, match="HTTP 401"):
        fetch_client_credentials_token(
            _CC, client=_client(lambda r: httpx.Response(401, text="nope")), timeout=10
        )


def test_non_json_raises() -> None:
    with pytest.raises(TokenFetchError, match="not valid JSON"):
        fetch_client_credentials_token(
            _CC, client=_client(lambda r: httpx.Response(200, text="<html>")), timeout=10
        )


def test_missing_access_token_raises() -> None:
    with pytest.raises(TokenFetchError, match="missing 'access_token'"):
        fetch_client_credentials_token(
            _CC,
            client=_client(lambda r: httpx.Response(200, json={"token_type": "Bearer"})),
            timeout=10,
        )


def test_unreachable_raises() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(TokenFetchError, match="unreachable"):
        fetch_client_credentials_token(_CC, client=_client(h), timeout=10)


# --------------------------------------------------------------- resolve
def test_resolve_passthrough_for_other_modes() -> None:
    for descriptor in (
        {"mode": "none"},
        {"mode": "bearer", "credential": "t"},
        {"mode": "api-key-header", "headerName": "X", "credential": "k"},
        {"mode": "basic", "username": "u", "password": "p"},
    ):
        assert resolve_auth_descriptor(descriptor) is descriptor


def test_resolve_client_credentials_derives_bearer() -> None:
    resolved = resolve_auth_descriptor(_CC, client=_client(_token_response), timeout=10)
    assert resolved == {"mode": "bearer", "credential": "AT"}


def test_resolve_propagates_token_failure() -> None:
    with pytest.raises(TokenFetchError):
        resolve_auth_descriptor(
            _CC, client=_client(lambda r: httpx.Response(500, text="x")), timeout=10
        )


# --------------------------------------------------------------- cache
def test_cached_token_reused_no_second_fetch() -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _token_response(request)

    client = _client(h)
    first = resolve_auth_descriptor(_CC, client=client, timeout=10)
    second = resolve_auth_descriptor(_CC, client=client, timeout=10)
    assert first == second == {"mode": "bearer", "credential": "AT"}
    assert len(calls) == 1  # second resolve served from cache


def test_expired_token_is_refetched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"access_token": f"AT{len(calls)}", "expires_in": 100})

    client = _client(h)
    clock = {"now": 1000.0}
    monkeypatch.setattr(oauth.time, "monotonic", lambda: clock["now"])

    first = resolve_auth_descriptor(_CC, client=client, timeout=10)
    clock["now"] += 200  # past the 100s lifetime (and the 30s skew)
    second = resolve_auth_descriptor(_CC, client=client, timeout=10)

    assert first == {"mode": "bearer", "credential": "AT1"}
    assert second == {"mode": "bearer", "credential": "AT2"}
    assert len(calls) == 2


def test_distinct_clients_cached_separately() -> None:
    calls: list[str] = []

    def h(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        calls.append(form["client_id"][0])
        return _token_response(request)

    client = _client(h)
    resolve_auth_descriptor(_CC, client=client, timeout=10)
    resolve_auth_descriptor({**_CC, "clientId": "other"}, client=client, timeout=10)
    assert calls == ["cid", "other"]  # different cache keys → two fetches


# --------------------------------------------------------------- use_cache / invalidate
def test_use_cache_false_always_fetches_and_does_not_populate() -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _token_response(request)

    client = _client(h)
    resolve_auth_descriptor(_CC, client=client, timeout=10, use_cache=False)
    resolve_auth_descriptor(_CC, client=client, timeout=10, use_cache=False)
    assert len(calls) == 2  # no cache read
    # And it never wrote to the cache, so a cached call afterward still fetches.
    resolve_auth_descriptor(_CC, client=client, timeout=10, use_cache=True)
    assert len(calls) == 3


def test_invalidate_token_forces_refetch() -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _token_response(request)

    client = _client(h)
    resolve_auth_descriptor(_CC, client=client, timeout=10)  # fetch + cache
    resolve_auth_descriptor(_CC, client=client, timeout=10)  # cache hit
    assert len(calls) == 1
    invalidate_token(_CC)  # e.g. after a secret rotation
    resolve_auth_descriptor(_CC, client=client, timeout=10)  # must refetch
    assert len(calls) == 2


def test_invalidate_token_noop_for_other_modes() -> None:
    invalidate_token({"mode": "bearer", "credential": "t"})  # must not raise
