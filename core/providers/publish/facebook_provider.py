"""
core/providers/publish/facebook_provider.py

CORRECTED. My first pass had the wrong API domain (graph-video vs the
real graph.facebook.com + rupload.facebook.com split), wrong API
version (v19.0 vs real v21.0), was missing the required
Content-Type: video/mp4 header on upload, and was missing the 8-second
sleep between the upload and finish phases. Rewritten to match the
real 3-step flow exactly.

Two things carried over from my first pass, both still correct:
- The "title": "Horror Story" -> now a parameter, as previously
  flagged and agreed (Audit Item 4) -- confirmed still hardcoded in
  the real file too, so that finding holds.
- Dry-run handling for missing/placeholder credentials, per your
  brief.
"""
import time
import requests
from .base import PublishProvider, PublishResult


class FacebookReelsProvider(PublishProvider):
    def __init__(self, page_id: str, access_token: str, is_dry_run: bool,
                 api_version: str = "v21.0"):
        self.page_id = page_id
        self.access_token = access_token
        self.is_dry_run = is_dry_run
        self.api_version = api_version

    def publish(self, video_path: str, title: str, caption: str) -> PublishResult:
        if self.is_dry_run:
            return PublishResult(
                success=True,
                dry_run=True,
                detail=(
                    f"DRY RUN: would publish '{title}' to page {self.page_id or '(unset)'} "
                    f"-- no Facebook Page/token configured for this brand yet."
                ),
            )

        try:
            import os
            file_size = os.path.getsize(video_path)

            init = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{self.page_id}/video_reels",
                data={"upload_phase": "start", "access_token": self.access_token},
            )
            init.raise_for_status()
            video_id = init.json()["video_id"]

            with open(video_path, "rb") as f:
                video_data = f.read()

            upload = requests.post(
                f"https://rupload.facebook.com/video-upload/{self.api_version}/{video_id}",
                headers={
                    "Authorization": f"OAuth {self.access_token}",
                    "offset": "0",
                    "file_size": str(file_size),
                    "Content-Type": "video/mp4",
                },
                data=video_data, timeout=300,
            )
            upload.raise_for_status()

            time.sleep(8)

            pub = requests.post(
                f"https://graph.facebook.com/{self.api_version}/{self.page_id}/video_reels",
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "title": title,
                    "description": caption,
                    "video_state": "PUBLISHED",
                    "access_token": self.access_token,
                },
            )
            pub.raise_for_status()

            return PublishResult(success=True, dry_run=False, post_id=video_id)
        except Exception as e:
            return PublishResult(success=False, dry_run=False, detail=str(e))
