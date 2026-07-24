from abc import ABC, abstractmethod


class MusicProvider(ABC):
    @abstractmethod
    def generate(self, mood_prompt: str, output_mp3_path: str) -> str:
        """Generate background music matching mood_prompt, return path
        to an MP3. Raise on failure -- caller decides fallback."""
        raise NotImplementedError
