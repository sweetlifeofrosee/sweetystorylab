from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PublishResult:
    success: bool
    dry_run: bool
    post_id: str = None
    detail: str = ""
    # Set by providers whose auth involves a rotating credential (e.g.
    # TikTok's refresh_token, which TikTok invalidates and replaces on
    # every use). None for providers with a static long-lived token
    # (Facebook's page token). When set, the caller MUST persist this
    # -- e.g. as an env-var pair, or an update to platform config --
    # regardless of whether `success` is True, since the old
    # credential may already be dead even if the publish attempt that
    # used the new one failed downstream.
    refreshed_credentials: Optional[dict] = None


class PublishProvider(ABC):
    @abstractmethod
    def publish(self, video_path: str, title: str, caption: str) -> PublishResult:
        """Publish a finished video. If credentials are missing or
        placeholder, MUST return a PublishResult(dry_run=True) instead
        of raising -- the pipeline should complete through video
        generation even when a brand's page doesn't exist yet."""
        raise NotImplementedError
