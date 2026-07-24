"""
core/story/parser_base.py

Core defines ONLY this interface. How raw LLM text becomes a Story is
entirely the brand's responsibility -- including formats as
genre-specific as Horror Lab's current fixed "Scene1Narration:" lines.

This keeps today's parser exactly as-is (preserving behavior) while
still giving the engine a stable, generic thing to call. A future
milestone can introduce a shared JSON-based parser as a NEW brand-
pluggable implementation, without touching this interface or core.
"""
from abc import ABC, abstractmethod
from .schema import Story


class StoryParser(ABC):
    @abstractmethod
    def parse(self, raw_text: str) -> Story:
        """Convert raw LLM output into a generic Story/Segment object.
        Brand-specific parsing logic (line formats, field names,
        assumed scene counts, etc.) lives entirely inside the
        implementation -- core never inspects it."""
        raise NotImplementedError
