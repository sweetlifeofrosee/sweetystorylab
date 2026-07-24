from abc import ABC, abstractmethod


class ImageProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, output_path: str) -> str:
        """Generate an image for `prompt`, save it to output_path,
        return the path. Providers handle their own retries/fallbacks
        internally and raise on unrecoverable failure."""
        raise NotImplementedError
