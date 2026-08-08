"""
tests/publish/test_tiktok_auth_exchange.py

Covers exchange_authorization_code() -- the new, additive function in
core/providers/publish/tiktok_auth.py. Does NOT touch
refresh_access_token() or its existing tests; that function is
untouched by this change and is not re-verified here.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.providers.publish.tiktok_auth import (
    TikTokAuthNetworkError,
    TikTokAuthorizationCodeInvalid,
    TokenPair,
    exchange_authorization_code,
)

_REDIRECT_URI = "https://sweetlifeofrosee.github.io/sweetystorylab/callback"


def _mock_response(status_code, json_body):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(str(status_code))
    else:
        resp.raise_for_status = MagicMock()
    return resp


def test_successful_exchange_returns_token_pair_and_sends_correct_grant_type():
    resp = _mock_response(200, {
        "access_token": "act.new123",
        "expires_in": 86400,
        "open_id": "oid-abc",
        "refresh_expires_in": 31536000,
        "refresh_token": "rft.new456",
        "scope": "user.info.basic,video.upload,video.publish",
        "token_type": "Bearer",
    })
    with patch("core.providers.publish.tiktok_auth.requests.post", return_value=resp) as mock_post:
        pair = exchange_authorization_code(
            client_key="key123", client_secret="secret456",
            code="AUTHCODE789", redirect_uri=_REDIRECT_URI,
        )

    assert pair == TokenPair(
        access_token="act.new123", refresh_token="rft.new456",
        expires_in=86400, open_id="oid-abc",
    )

    # Confirm the exact grant_type and redirect_uri sent -- these are
    # the two fields that distinguish this call from a refresh call,
    # and redirect_uri must match byte-for-byte per OAuth semantics.
    sent_data = mock_post.call_args.kwargs["data"]
    assert sent_data["grant_type"] == "authorization_code"
    assert sent_data["code"] == "AUTHCODE789"
    assert sent_data["redirect_uri"] == _REDIRECT_URI
    assert sent_data["client_key"] == "key123"
    assert sent_data["client_secret"] == "secret456"
    # grant_type=refresh_token must NEVER appear here -- that would
    # mean this function accidentally called the wrong grant type.
    assert "refresh_token" not in sent_data


def test_invalid_grant_raises_authorization_code_invalid_not_reauth_required():
    resp = _mock_response(400, {"error": "invalid_grant", "error_description": "code expired"})
    with patch("core.providers.publish.tiktok_auth.requests.post", return_value=resp):
        with pytest.raises(TikTokAuthorizationCodeInvalid):
            exchange_authorization_code(
                client_key="key", client_secret="secret",
                code="expired_code", redirect_uri=_REDIRECT_URI,
            )


def test_server_error_raises_network_error():
    resp = _mock_response(503, {})
    resp.text = "Service Unavailable"
    resp.json.side_effect = ValueError()
    with patch("core.providers.publish.tiktok_auth.requests.post", return_value=resp):
        with pytest.raises(TikTokAuthNetworkError):
            exchange_authorization_code(
                client_key="key", client_secret="secret",
                code="somecode", redirect_uri=_REDIRECT_URI,
            )


def test_malformed_200_response_raises_network_error():
    # Missing refresh_token and open_id
    resp = _mock_response(200, {"access_token": "act.x", "expires_in": 86400})
    with patch("core.providers.publish.tiktok_auth.requests.post", return_value=resp):
        with pytest.raises(TikTokAuthNetworkError):
            exchange_authorization_code(
                client_key="key", client_secret="secret",
                code="somecode", redirect_uri=_REDIRECT_URI,
            )


def test_connection_error_raises_network_error():
    with patch("core.providers.publish.tiktok_auth.requests.post",
               side_effect=requests.ConnectionError("boom")):
        with pytest.raises(TikTokAuthNetworkError):
            exchange_authorization_code(
                client_key="key", client_secret="secret",
                code="somecode", redirect_uri=_REDIRECT_URI,
            )


def test_credentials_never_appear_in_raised_exception_messages():
    """
    A raised exception's message must never leak client_secret or the
    authorization code -- both are sensitive, and exceptions often end
    up in logs/tracebacks.
    """
    resp = _mock_response(400, {"error": "invalid_grant", "error_description": "code expired"})
    with patch("core.providers.publish.tiktok_auth.requests.post", return_value=resp):
        with pytest.raises(TikTokAuthorizationCodeInvalid) as exc_info:
            exchange_authorization_code(
                client_key="key", client_secret="SUPER_SECRET_VALUE_XYZ",
                code="THE_ACTUAL_CODE_ABC", redirect_uri=_REDIRECT_URI,
            )
    message = str(exc_info.value)
    assert "SUPER_SECRET_VALUE_XYZ" not in message
    assert "THE_ACTUAL_CODE_ABC" not in message
