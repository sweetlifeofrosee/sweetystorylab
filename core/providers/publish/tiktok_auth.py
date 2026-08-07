"""
core/providers/publish/tiktok_auth.py

TikTok OAuth token refresh -- mechanics only.

DELIBERATE SCOPE BOUNDARY: this module knows how to turn a
(client_key, client_secret, refresh_token) into a new token pair by
calling TikTok's token endpoint. It does NOT know where tokens come
from before the call or where they go after -- no GitHub Actions
secrets API, no file writes, no env var mutation, no config.yaml
rewriting. The caller (a GitHub workflow step, a future
core/config/platform.py helper, a local CLI tool -- whatever) is
responsible for supplying the current refresh_token and persisting
the TokenPair this returns. This mirrors how FacebookReelsProvider
takes page_id/access_token as plain constructor args and never asks
where they came from.

Why this boundary matters in practice: storage is the part most
likely to change (repo secrets today, maybe an external secrets
manager later -- see the Phase 2 design conversation). Refresh
mechanics are TikTok's contract and won't change when storage does.
Keeping them separate means switching storage strategies never
touches this file, and this file is trivially testable without any
GitHub or filesystem dependency.

TOKEN ROTATION: TikTok's refresh endpoint may return a new
refresh_token alongside the new access_token -- when it does, the old
refresh_token is invalidated. This is TikTok's behavior, not a
possibility this module introduces. Callers MUST persist the returned
refresh_token (not just access_token) after every successful refresh,
or the next scheduled refresh will fail with invalid_grant once the
old one is used up. See TokenPair below -- both fields always
returned together, on purpose, so there's no code path that lets a
caller store one and forget the other.

RE-AUTHORIZATION: TikTok returns invalid_grant for a refresh attempt
whenever the refresh_token is dead for any reason -- expired past its
~365-day ceiling, the user revoked app access, the account password
changed, or the account is suspended/restricted. This module cannot
distinguish between those causes (TikTok's API doesn't either); it
surfaces all of them as TikTokReauthRequired so the caller can fail
loudly (log clearly, stop retrying, surface for manual
re-authorization) instead of treating it as a transient network error
worth retrying. Retrying a dead refresh_token wastes the 6
requests/minute budget for nothing.
"""
from dataclasses import dataclass
from typing import Optional

import requests

_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


class TikTokAuthError(Exception):
    """Base class for token-refresh failures."""


class TikTokReauthRequired(TikTokAuthError):
    """
    The refresh_token is dead and cannot be used again -- TikTok
    returned invalid_grant. Cause is indistinguishable from here
    (expired past ~365 days / user revoked access / password changed /
    account suspended -- see module docstring). The account owner must
    complete the OAuth authorization-code flow again from scratch;
    there is no programmatic recovery from this state.
    """


class TikTokAuthNetworkError(TikTokAuthError):
    """
    The refresh call itself failed before TikTok could evaluate the
    refresh_token (timeout, connection error, 5xx, malformed
    response). Distinct from TikTokReauthRequired on purpose: this is
    plausibly transient and safe to retry on the next scheduled run,
    unlike invalid_grant.
    """


@dataclass(frozen=True)
class TokenPair:
    """
    Always both fields together -- see module docstring on why a
    caller must never persist access_token without also persisting
    refresh_token in the same operation.
    """
    access_token: str
    refresh_token: str
    expires_in: int  # seconds, per TikTok's response (currently 86400 / 24h)
    open_id: str


def refresh_access_token(client_key: str, client_secret: str,
                          refresh_token: str, timeout: int = 30) -> TokenPair:
    """
    Exchange a refresh_token for a new TokenPair. Does not persist
    anything -- see module docstring. Does not require user
    interaction; this is the standard silent-refresh path TikTok's
    Login Kit describes, valid as long as refresh_token itself is
    still alive.

    Raises:
        TikTokReauthRequired: refresh_token is dead (see class docstring)
        TikTokAuthNetworkError: the request itself failed, or TikTok's
            response didn't match the documented shape -- worth a retry
            on a later run, not a re-auth
    """
    try:
        response = requests.post(
            _TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cache-Control": "no-cache",
            },
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise TikTokAuthNetworkError(f"Request to TikTok token endpoint failed: {e}") from e

    # TikTok returns invalid_grant with a 400 (or similar 4xx) for a
    # dead refresh_token -- checked before raise_for_status() so we
    # can classify it as TikTokReauthRequired instead of a generic
    # network error.
    if response.status_code != 200:
        body = _safe_json(response)
        error_code = body.get("error") if body else None
        if error_code == "invalid_grant":
            raise TikTokReauthRequired(
                "TikTok rejected the refresh_token (invalid_grant) -- "
                "re-authorization required. This is not recoverable by "
                "retrying; see TikTokReauthRequired docstring for causes."
            )
        detail = body.get("error_description") if body else response.text
        raise TikTokAuthNetworkError(
            f"TikTok token endpoint returned {response.status_code}: {detail}"
        )

    body = _safe_json(response)
    if body is None:
        raise TikTokAuthNetworkError(
            "TikTok token endpoint returned 200 but the response body "
            "wasn't valid JSON."
        )

    missing = [k for k in ("access_token", "refresh_token", "expires_in", "open_id")
               if k not in body]
    if missing:
        raise TikTokAuthNetworkError(
            f"TikTok token endpoint response is missing expected field(s) "
            f"{missing} -- response shape may have changed: {body}"
        )

    return TokenPair(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_in=body["expires_in"],
        open_id=body["open_id"],
    )


def _safe_json(response) -> Optional[dict]:
    try:
        return response.json()
    except ValueError:
        return None
