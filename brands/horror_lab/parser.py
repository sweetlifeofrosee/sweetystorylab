"""
brands/horror_lab/parser.py

This is a DELIBERATE, UNCHANGED port of the original post.py
`parse_story()`. It still hardcodes the "Scene1Narration:", "Title:",
"Question:" line format and still assumes exactly 3 narration scenes
+ 1 question slide, exactly as the current production script does.

That hardcoding is intentional at this milestone -- see Assumption
Audit item #1. It lives here, inside the brand folder, specifically
so core never has to know about it. If/when a generic JSON-based
parser is introduced (future milestone), this file becomes optional --
Horror Lab could adopt it or keep using this one; either way, no other
brand is affected.
"""
from core.story.parser_base import StoryParser
from core.story.schema import Segment, Story


class HorrorLabParser(StoryParser):
    def __init__(self, brand_id: str = "horror_lab"):
        self.brand_id = brand_id

    def parse(self, raw_text: str) -> Story:
        result = {
            "title": "Night Terror",
            "caption": "Some things are better left unseen. \U0001F47B",
            "hashtags": "#Horror #ScaryStories #GhostStories #Paranormal #SweetyStoryLab",
            "scenes": [{"narration": "", "image_prompt": ""} for _ in range(3)],
            "question": "Have you ever experienced something you cannot explain?",
            "narrator_gender": "male",
        }

        text = raw_text.replace("**", "").replace("*", "")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("Theme:"):
                pass  # logged only in the original; not part of the Story contract
            elif line.startswith("Title:"):
                result["title"] = line.replace("Title:", "").strip().strip('"')
            elif line.startswith("Caption:"):
                result["caption"] = line.replace("Caption:", "").strip().strip('"')
            elif line.startswith("Hashtags:"):
                result["hashtags"] = line.replace("Hashtags:", "").strip()
            elif line.startswith("NarratorGender:"):
                gender = line.replace("NarratorGender:", "").strip().lower()
                result["narrator_gender"] = "female" if "female" in gender else "male"
            elif line.startswith("Scene1Narration:"):
                result["scenes"][0]["narration"] = line.replace("Scene1Narration:", "").strip()
            elif line.startswith("Scene1Image:"):
                result["scenes"][0]["image_prompt"] = line.replace("Scene1Image:", "").strip()
            elif line.startswith("Scene2Narration:"):
                result["scenes"][1]["narration"] = line.replace("Scene2Narration:", "").strip()
            elif line.startswith("Scene2Image:"):
                result["scenes"][1]["image_prompt"] = line.replace("Scene2Image:", "").strip()
            elif line.startswith("Scene3Narration:"):
                result["scenes"][2]["narration"] = line.replace("Scene3Narration:", "").strip()
            elif line.startswith("Scene3Image:"):
                result["scenes"][2]["image_prompt"] = line.replace("Scene3Image:", "").strip()
            elif line.startswith("Question:"):
                result["question"] = line.replace("Question:", "").strip().strip('"')

        # Adapt the brand's private dict shape into the generic
        # Segment/Story contract that core requires downstream.
        segments = []
        for i, scene in enumerate(result["scenes"]):
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
            id=f"seg_{len(result['scenes'])}_question_slide",
            type="question_slide",
            order=len(result["scenes"]),
            text=result["question"],
            has_voiceover=False,
            duration_mode="fixed",
            duration_seconds=4.0,
        ))

        hashtags = result["hashtags"].split() if isinstance(result["hashtags"], str) else result["hashtags"]

        return Story(
            brand_id=self.brand_id,
            title=result["title"],
            caption=result["caption"],
            hashtags=hashtags,
            segments=segments,
            voice_profile=result["narrator_gender"],
        )
