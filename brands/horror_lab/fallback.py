"""
brands/horror_lab/fallback.py

Verbatim port of the real post.py FALLBACK dict, wrapped to implement
core's FallbackProvider interface. Core never sees this content --
it only ever calls get_fallback_story() and gets back a generic Story.
"""
from core.story.fallback_base import FallbackProvider
from core.story.schema import Segment, Story

_FALLBACK_SCENES = [
    {
        "narration": (
            "We moved into a new apartment last June. The neighbor warned us the "
            "moment we arrived. Nobody had lived on the third floor for years, she "
            "said, and nobody lasted more than a week when they tried. We laughed "
            "it off. The first week was quiet."
        ),
        "image_prompt": "dark apartment building hallway at night, flickering light, eerie fog, no people, cinematic horror",
    },
    {
        "narration": (
            "The second week, we heard footsteps every midnight. Slow, deliberate "
            "steps above us, though the floor was supposed to be empty. My husband "
            "Mark decided to go up and check. Ten minutes, he promised. He took his "
            "phone and the flashlight and headed up the stairwell alone."
        ),
        "image_prompt": "dark staircase leading up into darkness, single light at top, abandoned building, horror atmosphere",
    },
    {
        "narration": (
            "We found him two hours later, sitting in the corner of an empty room "
            "on the third floor. He was staring at the wall, completely still, not "
            "answering when we called his name. He came home with us without a "
            "word. To this day, he will not tell us what he saw up there."
        ),
        "image_prompt": "dark empty room corner with single dim light, eerie shadow on wall, abandoned, psychological horror",
    },
]

_FALLBACK_TITLE = "The Third Floor"
_FALLBACK_CAPTION = "He went up for ten minutes. He never came back the same. \U0001F47B"
_FALLBACK_HASHTAGS = (
    "#Horror #ScaryStories #GhostStories #Paranormal #Supernatural #HauntedPlace "
    "#TrueHorror #NightmareFuel #Creepy #Unexplained #DarkStories #HorrorShorts "
    "#StoryTime #Eerie #Thriller #SweetyStoryLab"
).split()
_FALLBACK_QUESTION = "Have you ever heard footsteps when nobody was there?"


class HorrorLabFallbackProvider(FallbackProvider):
    def __init__(self, brand_id: str = "horror_lab"):
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
