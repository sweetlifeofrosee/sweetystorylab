"""
core/story/schema.py

The generic data contract that flows between pipeline stages.
No field here should ever assume a genre, a scene count, or a closing
mechanic. If a brand needs something this schema can't express, that's
a signal to extend the schema deliberately -- not to bolt fields onto
one brand's private dict shape.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Segment:
    """One renderable unit of a story. `type` must match a key in the
    core renderer registry (core/renderers/registry.py). Everything
    else is content, filled in by the LLM according to the brand's
    prompt."""
    id: str
    type: str
    order: int
    narration: Optional[str] = None     # spoken text, if any
    text: Optional[str] = None          # on-screen-only text (e.g. a
                                         # closing prompt with no voiceover)
    image_prompt: Optional[str] = None
    has_voiceover: bool = True
    duration_mode: str = "audio_length"  # "audio_length" | "fixed"
    duration_seconds: Optional[float] = None  # required if duration_mode == "fixed"


@dataclass
class Story:
    """The full generated content for one post, independent of genre."""
    brand_id: str
    title: str
    caption: str
    hashtags: list = field(default_factory=list)
    segments: list = field(default_factory=list)  # list[Segment], ordered
    # Opaque key the brand's config maps to actual voice settings, e.g.
    # "male" / "female" / "detective" / "narrator_a". Core never
    # interprets this string -- it's just a lookup key forwarded to
    # whatever the brand's `voices:` config declares.
    voice_profile: str = None
    # Optional: the story's primary historical/factual subject, if the
    # brand's parser captures one (e.g. Mystery Lab's "Theme:" line).
    # None for brands that don't populate it (e.g. Horror Lab) --
    # purely additive, core does not require or interpret this field
    # except when a brand-supplied dedup checker uses it (see engine.py).
    primary_subject: str = None

    def narration_segments(self):
        return [s for s in self.segments if s.narration]

    def full_narration_text(self) -> str:
        """Concatenated narration across all voiced segments, in order.
        Used for single-pass TTS generation (current approach: one
        audio file for the whole story, timed back onto segments)."""
        ordered = sorted(self.narration_segments(), key=lambda s: s.order)
        return " ".join(s.narration for s in ordered)