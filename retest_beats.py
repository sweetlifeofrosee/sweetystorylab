"""
retest_beats.py

Reruns subtitle beat-splitting AND frame re-composition (title,
watermark, question-slide -- whatever the current LayoutProfile
affects) against a PREVIOUSLY GENERATED story's assets on disk. Makes
no LLM or TTS API calls. Image re-composition is pure local Pillow
work (no Pollinations call) -- it reuses the already-downloaded raw
source image, it does not generate a new one.

IMPORTANT: frames are ALWAYS re-rendered fresh from the cached raw
source image + whatever layout_profiles.py currently contains. This is
not optional -- watermark position, title position, and question-slide
position are baked into the composited frame_*.jpg at render time, not
redrawn by ffmpeg at burn time (only subtitles are). An earlier version
of this script reused the old frame_*.jpg files directly, which meant
watermark/title changes silently didn't show up in retests -- only
subtitle changes did, since those really are re-applied fresh by
ffmpeg every run. If you're only iterating on subtitle_beat_max_chars
or subtitle_target_margin_px, this extra step costs nothing (still zero
API calls) -- it's the same story_dir either way.

Usage:
    python retest_beats.py <story_dir> [--platform facebook|tiktok] [--brands-root brands]

<story_dir> is a folder that already contains, from a previous run:
    story.json
    voice.mp3
    voice.srt
    img_<segment.id>.jpg   (raw source image per segment, BEFORE title/watermark/etc)

This is exactly the shape of a folder produced by:
    python -m core.pipeline.cli --brand horror_lab --count 1
under output/<brand>/<timestamp>/story_01/, or the work_dir of a
normal (non --count) run.

Output: <story_dir>/final_beats_retest.mp4
"""
import argparse
import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.story.schema import Story, Segment
from core.config.loader import load_brand_config
from core.subtitles.beat_splitter import rewrite_srt_as_beats
from core.renderers.layout_profiles import get_profile
from core.renderers.registry import render_segment, get_spec
from core.pipeline.run import RenderContext
from core.video.assembler import build_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("story_dir", help="Folder with story.json, voice.mp3, voice.srt, img_*.jpg")
    parser.add_argument("--platform", default="facebook", choices=["facebook", "tiktok"])
    parser.add_argument("--brands-root", default="brands",
                         help="Where brand configs live, relative to this script's cwd (default: brands)")
    args = parser.parse_args()

    story_dir = os.path.abspath(args.story_dir)
    layout_profile = get_profile(args.platform)

    with open(os.path.join(story_dir, "story.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = [Segment(**s) for s in data["segments"]]
    story = Story(**{**data, "segments": segments})

    voice_path = os.path.join(story_dir, "voice.mp3")
    srt_path = os.path.join(story_dir, "voice.srt")
    if not os.path.exists(voice_path) or not os.path.exists(srt_path):
        print(f"Missing voice.mp3 or voice.srt in {story_dir} -- "
              f"this folder wasn't produced by a full run.", file=sys.stderr)
        sys.exit(1)

    brand_dir = os.path.join(args.brands_root, story.brand_id)
    config = load_brand_config(brand_dir)
    font_path = os.path.join(brand_dir, config.font_file)
    narration_scene_count = sum(
        1 for s in story.segments if get_spec(s.type)["defaults"]["duration_mode"] == "audio_length"
    )

    # Re-render every frame fresh -- see module docstring for why this
    # can't be skipped even when only testing a subtitle-only change.
    rendered_segments = []
    narration_index = 0
    last_image_path = None
    missing_raw_images = []
    for seg in sorted(story.segments, key=lambda s: s.order):
        raw_image_path = os.path.join(story_dir, f"img_{seg.id}.jpg")
        if seg.image_prompt:
            if not os.path.exists(raw_image_path):
                missing_raw_images.append(raw_image_path)
                continue
            last_image_path = raw_image_path

        ctx = RenderContext(
            work_dir=story_dir,
            title=story.title,
            watermark_text=config.watermark_text,
            font_path=font_path,
            total_narration_scenes=narration_scene_count,
            question_max_font_size=config.question_max_font_size,
            question_text_color=config.question_text_color,
            layout_profile=layout_profile,
        )
        ctx.image_path = raw_image_path if seg.image_prompt else last_image_path
        ctx.scene_index = narration_index
        if get_spec(seg.type)["defaults"]["duration_mode"] == "audio_length":
            narration_index += 1

        frame_path = render_segment(seg, ctx)
        rendered_segments.append((frame_path, seg))

    if missing_raw_images:
        print(f"Missing {len(missing_raw_images)} raw source image(s), e.g. "
              f"{missing_raw_images[0]} -- this story_dir predates raw-image "
              f"caching, or was hand-built. Can't re-render frames without it.",
              file=sys.stderr)
        sys.exit(1)

    beats_srt_path = os.path.join(story_dir, "voice_beats_retest.srt")
    rewrite_srt_as_beats(srt_path, beats_srt_path,
                          max_chars=layout_profile.subtitle_beat_max_chars)

    music_path = None
    for candidate in os.listdir(story_dir):
        if candidate.endswith((".mp3", ".wav")) and candidate != "voice.mp3":
            music_path = os.path.join(story_dir, candidate)
            break

    output_path = os.path.join(story_dir, "final_beats_retest.mp4")
    build_video(rendered_segments, voice_path, beats_srt_path, story_dir, output_path,
                music_path, layout_profile=layout_profile)

    print(f"Done -- no API calls made. Reused:")
    print(f"  story.json, {len(rendered_segments)} raw source image(s), voice.mp3, voice.srt")
    print(f"Re-rendered {len(rendered_segments)} frame(s) fresh with the current layout_profile")
    print(f"New beat-split subtitles: {beats_srt_path}")
    print(f"Output video: {output_path}")


if __name__ == "__main__":
    main()