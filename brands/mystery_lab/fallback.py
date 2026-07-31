"""
brands/mystery_lab/fallback.py

Mystery Lab's static, hand-written fallback story -- used when live
generation fails or produces an incomplete Story. Same shape as
brands/horror_lab/fallback.py: core never sees this content, it only
calls get_fallback_story() and gets back a generic Story.

Subject chosen deliberately: the Voynich Manuscript. See the
explanation accompanying this file for the reasoning.
"""
from core.story.fallback_base import FallbackProvider
from core.story.schema import Segment, Story

_FALLBACK_SCENES = [
    {
        "narration": (
            "In a library at Yale University sits a book no one has ever been "
            "able to read. Its pages are filled with flowing, unfamiliar script "
            "and illustrations of plants that match no known species. It is "
            "known simply as the Voynich Manuscript."
        ),
        "image_prompt": "muted documentary photography, old handwritten manuscript on wooden table, archival tone, desaturated color, no people, no text",
    },
    {
        "narration": (
            "Radiocarbon dating places its parchment in the early 1400s, and "
            "that much is not disputed. What the text itself says, however, "
            "remains completely unknown. Its script matches no confirmed "
            "language, and a century of cryptographic effort has failed to "
            "translate a single page."
        ),
        "image_prompt": "muted documentary photography, close-up of unknown handwritten script, archival tone, desaturated color, no people, no text",
    },
    {
        "narration": (
            "Some researchers have proposed it is an unrecorded language. "
            "Others suggest an elaborate cipher, or even a deliberate hoax "
            "created to deceive a wealthy buyer. Each theory has supporters. "
            "None has been confirmed."
        ),
        "image_prompt": "muted documentary photography, old library shelves and archives, archival tone, desaturated color, no people, no text, evocative",
    },
]

_FALLBACK_TITLE = "The Book No One Can Read"
_FALLBACK_CAPTION = "A 600-year-old book that still defies every expert. \U0001F4DC"
_FALLBACK_HASHTAGS = (
    "#MysteryLab #HistoryStillHasSecrets #UnsolvedMysteries #HistoricalMystery "
    "#StrangeArtifacts #HistoricalEnigma #VoynichManuscript #TrueHistory "
    "#StillUnsolved #HistoryLovers #DidYouKnow #HiddenHistory"
).split()
_FALLBACK_QUESTION = "What would it mean if someone finally read it?"


class MysteryLabFallbackProvider(FallbackProvider):
    def __init__(self, brand_id: str = "mystery_lab"):
        self.brand_id = brand_id

    def get_fallback_story(self) -> Story:
        segments = []
        for i, scene in enumerate(_FALLBACK_SCENES):
            segments.append(Segment(
                id=f"seg_{i}_narration_scene",
                type="narration_scene",
                order=i,
                narration=scene["narration"],
                image_prompt=scene["image_prompt"],
                has_voiceover=True,
                duration_mode="audio_length",
            ))
        segments.append(Segment(
            id=f"seg_{len(_FALLBACK_SCENES)}_question_slide",
            type="question_slide",
            order=len(_FALLBACK_SCENES),
            text=_FALLBACK_QUESTION,
            has_voiceover=False,
            duration_mode="fixed",
            duration_seconds=4.0,
        ))
        return Story(
            brand_id=self.brand_id,
            title=_FALLBACK_TITLE,
            caption=_FALLBACK_CAPTION,
            hashtags=_FALLBACK_HASHTAGS,
            segments=segments,
            voice_profile="male",
        )
