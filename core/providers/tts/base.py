from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @abstractmethod
    def generate(self, text: str, voice_file: str) -> bool:
        """Attempt to generate narration audio for `text`, saved to
        voice_file. Return True on success, False on recoverable
        failure (e.g. quota exceeded) so the caller can fall back to
        the next provider in the chain. Should not raise for expected
        failure modes -- only for genuinely unexpected errors."""
        raise NotImplementedError
