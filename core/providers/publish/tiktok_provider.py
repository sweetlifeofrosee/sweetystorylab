"""
core/providers/publish/tiktok_provider.py

TikTokProvider implements PublishProvider the same way
FacebookReelsProvider does -- publish(video_path, title, caption) ->
PublishResult -- so it plugs into run_brand()'s existing platform
branch without that branch needing to know anything TikTok-specific.

Where this necessarily differs from Facebook, and why:

- Auth: TikTok's access_token is short-lived (~24h) and its
  refresh_token rotates on every use (see tiktok_auth.py). This
  provider refreshes once at the start of every publish() call --
  it does not try to cache/reuse an access_token across calls, since
  each scheduled run is a fresh process anyway and TikTok's flow is
  "refresh then use immediately." The refreshed pair is returned via
  PublishResult.refreshed_credentials for the caller to persist --
  this module has no opinion on how (see tiktok_auth.py's module
  docstring for the reasoning).

- Creator Info query: TikTok's own posting guidelines require calling
  creator_info/query immediately before a post, to (a) get the
  privacy_level options actually available to this account -- which
  is how the "unaudited apps are forced to SELF_ONLY" restriction
  surfaces, as options rather than a documented flag -- and (b) get
  the account's current duet/comment/stitch-disabled settings, which
  must be echoed back in the publish request. This is not optional
  ceremony; skipping it and hardcoding privacy_level risks the API
  rejecting the request outright.

- Chunked upload: TikTok's FILE_UPLOAD source requires the caller to
  pre-declare chunk_size/total_chunk_count and PUT each chunk with an
  explicit Content-Range header, rather than Facebook's single-shot
  body upload. In practice StoryFactory's rendered vertical shorts are
  almost always under the 64MB single-chunk ceiling, so this usually
  runs as one chunk -- but the general multi-chunk path is
  implemented rather than assumed away, since a longer or
  higher-bitrate render could cross that line later.

- Async publish: unlike Facebook's synchronous finish call, TikTok's
  init call returns immediately and the actual publish happens async
  server-side; this provider polls status/fetch until it leaves
  PROCESSING.

Audit-mode awareness: until this app passes TikTok's review, every
post is forced to SELF_ONLY regardless of what's requested. This
provider doesn't try to detect that as an error -- it's expected
behavior pre-audit -- but it does say so plainly in `detail` when the
chosen privacy_level is SELF_ONLY, so a real publish doesn't read as a
silent success when the video is actually private.
"""
import os
import time
from typing import Optional

import requests

from .base import PublishProvider, PublishResult
from .tiktok_auth import (
    refresh_access_token,
    TikTokReauthRequired,
    TikTokAuthNetworkError,
)

_API_BASE = "https://open.tiktokapis.com/v2"

# Per TikTok's Content Posting API docs: non-final chunks must be
# between 5MB and 64MB; the final chunk may exceed chunk_size, up to
# 128MB, to absorb the remainder. Videos <=64MB total go up as a
# single chunk.
_MIN_CHUNK = 5 * 1024 * 1024
_MAX_CHUNK = 64 * 1024 * 1024
_MAX_FINAL_CHUNK = 128 * 1024 * 1024

# TikTok's documented cap on the title/caption field. Truncated
# defensively rather than left to fail at the API -- if this proves
# wrong against a real post, widen it.
_MAX_TITLE_CHARS = 2200

_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 180


class TikTokProvider(PublishProvider):
    def __init__(self, client_key: str, refresh_token: str, is_dry_run: bool,
                 client_secret: Optional[str] = None):
        self.client_key = client_key
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.is_dry_run = is_dry_run

    def publish(self, video_path: str, title: str, caption: str) -> PublishResult:
        if self.is_dry_run:
            return PublishResult(
                success=True,
                dry_run=True,
                detail=(
                    "DRY RUN: would publish to TikTok -- no client_key/"
                    "refresh_token configured for this brand yet."
                ),
            )

        # --- Refresh first. Whatever happens after this point, the
        # new token pair (if we got one) must be surfaced for the
        # caller to persist, since the old refresh_token may already
        # be dead from this call alone (TikTok rotates on use).
        try:
            token_pair = refresh_access_token(
                self.client_key, self.client_secret, self.refresh_token
            )
        except TikTokReauthRequired as e:
            return PublishResult(
                success=False, dry_run=False,
                detail=f"TikTok re-authorization required: {e}",
            )
        except TikTokAuthNetworkError as e:
            return PublishResult(
                success=False, dry_run=False,
                detail=f"TikTok token refresh failed (transient, safe to retry): {e}",
            )

        refreshed = {
            "access_token": token_pair.access_token,
            "refresh_token": token_pair.refresh_token,
            "expires_in": token_pair.expires_in,
            "open_id": token_pair.open_id,
        }
        access_token = token_pair.access_token

        try:
            creator_info = self._query_creator_info(access_token)
        except Exception as e:
            return PublishResult(
                success=False, dry_run=False,
                detail=f"TikTok creator_info query failed: {e}",
                refreshed_credentials=refreshed,
            )

        privacy_level = _choose_privacy_level(creator_info.get("privacy_level_options", []))

        try:
            file_size = os.path.getsize(video_path)
            chunk_size, total_chunk_count = _compute_chunk_plan(file_size)

            publish_id, upload_url = self._init_upload(
                access_token=access_token,
                title=_truncate_title(title, caption),
                privacy_level=privacy_level,
                creator_info=creator_info,
                video_size=file_size,
                chunk_size=chunk_size,
                total_chunk_count=total_chunk_count,
            )

            self._upload_chunks(upload_url, video_path, file_size, chunk_size, total_chunk_count)

            status, fail_reason = self._poll_status(access_token, publish_id)

            if status == "PUBLISH_COMPLETE":
                detail = ""
                if privacy_level == "SELF_ONLY":
                    detail = (
                        "Published as SELF_ONLY (private) -- expected while this "
                        "app is unaudited by TikTok; not publicly visible yet."
                    )
                return PublishResult(
                    success=True, dry_run=False, post_id=publish_id,
                    detail=detail, refreshed_credentials=refreshed,
                )
            else:
                return PublishResult(
                    success=False, dry_run=False, post_id=publish_id,
                    detail=f"TikTok publish did not complete (status={status}): {fail_reason}",
                    refreshed_credentials=refreshed,
                )

        except Exception as e:
            return PublishResult(
                success=False, dry_run=False,
                detail=str(e),
                refreshed_credentials=refreshed,
            )

    # -- internal steps --------------------------------------------------

    def _query_creator_info(self, access_token: str) -> dict:
        resp = requests.post(
            f"{_API_BASE}/post/publish/creator_info/query/",
            headers=_auth_headers(access_token),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        _raise_if_api_error(body)
        return body.get("data", {})

    def _init_upload(self, access_token: str, title: str, privacy_level: str,
                      creator_info: dict, video_size: int, chunk_size: int,
                      total_chunk_count: int) -> tuple:
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                # Echo the account's current settings back rather than
                # assuming all-enabled -- creator_info reflects what
                # the account actually allows right now.
                "disable_duet": creator_info.get("duet_disabled", False),
                "disable_comment": creator_info.get("comment_disabled", False),
                "disable_stitch": creator_info.get("stitch_disabled", False),
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        }
        resp = requests.post(
            f"{_API_BASE}/post/publish/video/init/",
            headers={**_auth_headers(access_token), "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        _raise_if_api_error(body)
        data = body["data"]
        return data["publish_id"], data["upload_url"]

    def _upload_chunks(self, upload_url: str, video_path: str, file_size: int,
                        chunk_size: int, total_chunk_count: int) -> None:
        with open(video_path, "rb") as f:
            for i in range(total_chunk_count):
                start = i * chunk_size
                is_last = i == total_chunk_count - 1
                end = file_size - 1 if is_last else start + chunk_size - 1
                length = end - start + 1

                chunk = f.read(length)
                resp = requests.put(
                    upload_url,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Type": "video/mp4",
                    },
                    data=chunk,
                    timeout=300,
                )
                resp.raise_for_status()

    def _poll_status(self, access_token: str, publish_id: str) -> tuple:
        deadline = time.time() + _POLL_TIMEOUT_SECONDS
        while time.time() < deadline:
            resp = requests.post(
                f"{_API_BASE}/post/publish/status/fetch/",
                headers={**_auth_headers(access_token), "Content-Type": "application/json"},
                json={"publish_id": publish_id},
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            _raise_if_api_error(body)
            data = body["data"]
            status = data.get("status")
            if status != "PROCESSING_UPLOAD" and status != "PROCESSING_DOWNLOAD":
                return status, data.get("fail_reason", "")
            time.sleep(_POLL_INTERVAL_SECONDS)
        return "TIMEOUT", f"No terminal status within {_POLL_TIMEOUT_SECONDS}s"


# -- module-level helpers -------------------------------------------------

def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _raise_if_api_error(body: dict) -> None:
    error = body.get("error", {})
    code = error.get("code")
    if code and code != "ok":
        raise RuntimeError(f"TikTok API error ({code}): {error.get('message', '')}")


def _choose_privacy_level(options: list) -> str:
    """
    Prefer public if this app/account is actually allowed to post
    publicly; otherwise take whatever TikTok does offer. An unaudited
    app's creator_info response will simply not list
    PUBLIC_TO_EVERYONE among options -- that's how the audit
    restriction actually shows up, not as a separate flag.
    """
    if "PUBLIC_TO_EVERYONE" in options:
        return "PUBLIC_TO_EVERYONE"
    if "SELF_ONLY" in options:
        return "SELF_ONLY"
    if options:
        return options[0]
    # No options returned at all -- fall back to the safest choice
    # rather than fail outright; SELF_ONLY is always valid per TikTok's docs.
    return "SELF_ONLY"


def _truncate_title(title: str, caption: str) -> str:
    """
    TikTok's video post has a single `title` field that functions as
    the post's caption (unlike Facebook's separate title/description).
    StoryFactory's caption already carries the hashtags, so caption is
    the primary text; title is prepended only if caption doesn't
    already start with it, to avoid an awkward double-heading.
    """
    if caption.strip().startswith(title.strip()):
        combined = caption.strip()
    else:
        combined = f"{title.strip()}\n\n{caption.strip()}".strip()
    if len(combined) > _MAX_TITLE_CHARS:
        combined = combined[:_MAX_TITLE_CHARS]
    return combined


def _compute_chunk_plan(video_size: int) -> tuple:
    if video_size <= _MAX_CHUNK:
        return video_size, 1

    chunk_size = _MAX_CHUNK
    total_chunk_count = video_size // chunk_size
    remainder = video_size - (total_chunk_count * chunk_size)

    # If the remainder would make the final chunk exceed the 128MB
    # ceiling, add another chunk rather than overflow it.
    final_chunk_size = chunk_size + remainder
    if final_chunk_size > _MAX_FINAL_CHUNK:
        total_chunk_count += 1

    return chunk_size, total_chunk_count
