from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PublishResult:
    success: bool
    dry_run: bool
    post_id: str = None
    detail: str = ""


class PublishProvider(ABC):
    @abstractmethod
    def publish(self, video_path: str, title: str, caption: str) -> PublishResult:
        """Publish a finished video. If credentials are missing or
        placeholder, MUST return a PublishResult(dry_run=True) instead
        of raising -- the pipeline should complete through video
        generation even when a brand's page doesn't exist yet."""
        raise NotImplementedError
