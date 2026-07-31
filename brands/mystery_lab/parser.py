"""
brands/mystery_lab/parser.py

Independent implementation, deliberately NOT sharing code with
brands/horror_lab/parser.py. The parsing algorithm below is
mechanically similar to HorrorLabParser -- both brands use the same
output schema (Theme/Title/Caption/Hashtags/NarratorGender/SceneN.../
Question) by design, so the line-matching logic is naturally close to
identical.

This duplication is intentional, not an oversight: brand isolation and
architectural clarity were judged more valuable than eliminating a
small, mechanical amount of duplication at this stage. Revisit only if
a THIRD brand adopts this same line-format and demonstrates a real,
repeated maintenance cost -- not before.
"""
from core.story.parser_base import StoryParser
from core.story.schema import Segment, Story


class MysteryLabParser(StoryParser):
    def __init__(self, brand_id: str = "mystery_lab"):
        self.brand_id = brand_id

    def parse(self, raw_text: str) -> Story:
        result = {
            "title": "The Unsolved Case",
            "caption": "History still has secrets. \U0001F4DC",
            "hashtags": "#MysteryLab #HistoryStillHasSecrets #UnsolvedMysteries #HistoricalMystery",
            "scenes": [{"narration": "", "image_prompt": ""} for _ in range(3)],
            "question": "What do you think really happened?",
            "narrator_gender": "male",
            "primary_subject": None,
        }

        text = raw_text.replace("**", "").replace("*", "")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("PrimarySubject:"):
                result["primary_subject"] = line.replace("PrimarySubject:", "").strip().strip('"')
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
        # Segment/Story contract core requires downstream -- identical
        # adaptation shape to Horror Lab, since the schema is identical.
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
            primary_subject=result["primary_subject"],
        )