"""
core/pipeline/run.py

The orchestrator. This is the one module that knows the *sequence* of
stages -- but never their *content*. It loads a brand by id, resolves
that brand's own prompt files + parser + config, and drives the
generic providers/renderers. No brand_id branching anywhere below.
"""
import importlib
import os
import tempfile

from ..config.loader import load_brand_config
from ..config import platform as platform_config
from ..story.engine import generate_story
from ..renderers.registry import render_segment, get_spec
from ..providers.llm.groq_provider import GroqProvider
from ..providers.image.pollinations_provider import PollinationsProvider
from ..providers.tts.edge_tts_provider import EdgeTTSProvider
from ..providers.tts.elevenlabs_provider import ElevenLabsProvider
from ..providers.tts.orchestrator import generate_voice
from ..providers.music.local_file_provider import LocalFileMusicProvider
from ..providers.publish.facebook_provider import FacebookReelsProvider
from ..video.assembler import build_video
from ..storage.log_store import init_db, log_result


class RenderContext:
    """Passed to every renderer -- see core/renderers/*. Carries brand
    styling so renderers stay generic across brands."""
    def __init__(self, work_dir, title, watermark_text, font_path,
                 total_narration_scenes, question_max_font_size=None,
                 question_text_color=None):
        self.work_dir = work_dir
        self.title = title
        self.watermark_text = watermark_text
        self.font_path = font_path
        self.total_narration_scenes = total_narration_scenes
        self.question_max_font_size = question_max_font_size
        self.question_text_color = question_text_color
        self.image_path = None  # set per-segment before rendering
        self.scene_index = 0    # set per-segment before rendering


def run_brand(brand_id: str, brands_root: str = "brands", db_path: str = "posts.db",
              force_dry_run: bool = False, dedup_kwargs: dict = None):
    """force_dry_run is purely a developer/testing convenience (see
    run_brand_batch below) -- when True, publishing is skipped
    regardless of whether real credentials exist. Default behavior
    (force_dry_run=False) is completely unchanged from before this
    parameter existed.

    dedup_kwargs: optional, generic passthrough to a brand's dedup
    module constructor (e.g. {"storage_path": "..."} to isolate a test
    run's dedup history from the canonical production file). Core does
    not interpret these kwargs -- it's an informal convention any
    dedup_module a brand supplies may honor, the same way brand parsers
    and fallback providers all accept `brand_id=`. Defaults to None,
    meaning the dedup module uses its own default persistence location
    (the canonical, production file)."""
    brand_dir = os.path.join(brands_root, brand_id)
    config = load_brand_config(brand_dir)

    with open(os.path.join(brand_dir, config.system_prompt_file)) as f:
        system_prompt = f.read()
    with open(os.path.join(brand_dir, config.user_prompt_file)) as f:
        user_prompt = f.read()

    parser_module_path, parser_class_name = config.parser_module.rsplit(".", 1)
    parser_module = importlib.import_module(parser_module_path)
    parser = getattr(parser_module, parser_class_name)(brand_id=brand_id)

    fallback_module_path, fallback_class_name = config.fallback_provider_module.rsplit(".", 1)
    fallback_module = importlib.import_module(fallback_module_path)
    fallback_provider = getattr(fallback_module, fallback_class_name)(brand_id=brand_id)

    # OPTIONAL -- most brands (e.g. Horror Lab) won't set this, and
    # dedup_checker stays None, meaning generate_story() behaves exactly
    # as it always has (single attempt, no retry loop).
    dedup_checker = None
    if config.dedup_module:
        dedup_module_path, dedup_class_name = config.dedup_module.rsplit(".", 1)
        dedup_module = importlib.import_module(dedup_module_path)
        dedup_checker = getattr(dedup_module, dedup_class_name)(
            brand_id=brand_id, **(dedup_kwargs or {})
        )

    llm = GroqProvider(api_key=platform_config.get_groq_api_key(), model=config.llm_model)
    story = generate_story(llm, system_prompt, user_prompt, parser,
                            fallback_provider=fallback_provider,
                            dedup_checker=dedup_checker,
                            temperature=config.llm_temperature,
                            max_tokens=config.llm_max_tokens)

    work_dir = tempfile.mkdtemp(prefix=f"{brand_id}_")
    font_path = os.path.join(brand_dir, config.font_file)

    narration_scene_count = sum(
        1 for s in story.segments if get_spec(s.type)["defaults"]["duration_mode"] == "audio_length"
    )

    image_fallback_path = (
        os.path.join(brand_dir, config.image_fallback_dir)
        if config.image_fallback_dir else None
    )
    image_provider = PollinationsProvider(style_suffix=config.image_style_suffix,
                                           fallback_dir=image_fallback_path)
    rendered_segments = []
    narration_index = 0
    last_image_path = None
    for segment in sorted(story.segments, key=lambda s: s.order):
        image_path = os.path.join(work_dir, f"img_{segment.id}.jpg")
        if segment.image_prompt:
            try:
                image_provider.generate(segment.image_prompt, image_path, index=narration_index)
            except Exception:
                # Matches the real post.py main() except-block fallback
                # behavior (a plain frame if Pollinations AND the local
                # fallback image both fail), but the color is now brand
                # config instead of a hardcoded near-black literal --
                # see Assumption Audit / architecture review Finding 4.
                from PIL import Image as _Image
                _Image.new("RGB", (1080, 1080), config.image_fallback_color).save(image_path, "JPEG")
            last_image_path = image_path

        ctx = RenderContext(
            work_dir=work_dir,
            title=story.title,
            watermark_text=config.watermark_text,
            font_path=font_path,
            total_narration_scenes=narration_scene_count,
            question_max_font_size=config.question_max_font_size,
            question_text_color=config.question_text_color,
        )
        # Segments with no image_prompt of their own (e.g. question_slide)
        # reuse the most recently generated narration image as their
        # background -- matches the original build_question_frame()
        # behavior of reusing the last scene's image.
        ctx.image_path = image_path if segment.image_prompt else last_image_path
        ctx.scene_index = narration_index
        if get_spec(segment.type)["defaults"]["duration_mode"] == "audio_length":
            narration_index += 1

        frame_path = render_segment(segment, ctx)
        rendered_segments.append((frame_path, segment))

    voice_path = os.path.join(work_dir, "voice.mp3")
    srt_path = os.path.join(work_dir, "voice.srt")

    # Core never interprets voice_profile -- it's an opaque key the
    # brand defines (e.g. "male"/"female", or "detective"/"witness"
    # for a future brand). This is purely a config lookup.
    profile_key = story.voice_profile or config.voice_default_profile
    profile = config.voice_profiles.get(profile_key, {})

    eleven_key = platform_config.get_elevenlabs_api_key()
    primary = (
        ElevenLabsProvider(eleven_key, profile.get("elevenlabs_preferred", []))
        if eleven_key else None
    )
    fallback = EdgeTTSProvider(profile.get("edge_tts_voice"))
    tts_used = generate_voice(story.full_narration_text(), voice_path, srt_path,
                               primary_provider=primary, fallback_provider=fallback)

    music_local_path = (
        os.path.join(brand_dir, config.music_local_file)
        if config.music_local_file else None
    )
    music_provider = LocalFileMusicProvider(file_path=music_local_path)
    music_path = music_provider.generate()

    output_path = os.path.join(work_dir, "final.mp4")
    build_video(rendered_segments, voice_path, srt_path, work_dir, output_path, music_path)

    publisher = FacebookReelsProvider(
        page_id=config.facebook.page_id,
        access_token=config.facebook.access_token,
        is_dry_run=(config.facebook.is_dry_run or force_dry_run),
    )
    # CORRECTED (architecture review): real post.py uses
    # f"{caption}\n\n{hashtags}" -- this previously used a single
    # space, never verified until now. Real parity, not a style choice.
    caption = f"{story.caption}\n\n{' '.join(story.hashtags)}"
    publish_result = publisher.publish(output_path, story.title, caption)

    init_db(db_path)
    status = "success" if (publish_result.success or publish_result.dry_run) else "failed"
    log_result(db_path, brand_id, story.title, publish_result.post_id,
               status, publish_result.detail if not publish_result.success else None)

    return {
        "story": story,
        "video_path": output_path,
        "publish_result": publish_result,
        "work_dir": work_dir,
        "tts_used": tts_used,
        "srt_path": srt_path,
    }


def run_brand_batch(brand_id: str, count: int, brands_root: str = "brands",
                     output_root: str = "output"):
    """Developer/testing convenience: generate `count` completely
    independent stories in one run, never publishing, saving each
    story's full output (generated story JSON, images, video,
    subtitles, metadata, and its own per-story log) into its own
    numbered folder for easy comparison:

        output/<brand_id>/<timestamp>/story_01/
        output/<brand_id>/<timestamp>/story_02/
        ...

    Purely additive on top of run_brand() -- no schema, renderer,
    prompt, or registry changes; no brand-specific logic here either.
    """
    import dataclasses
    import json
    import shutil
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = os.path.join(output_root, brand_id, timestamp)
    os.makedirs(batch_dir, exist_ok=True)

    # Isolate this batch's dedup history from the canonical production
    # file: computed once, before the loop, so all N stories in THIS
    # batch still correctly dedupe against each other (matching normal
    # production behavior), but this batch never reads or writes the
    # real used_subjects.json, and no state carries over to a future
    # --count invocation either. Brands without a dedup_module simply
    # never look at this dict, so it's harmless to always build it.
    batch_dedup_kwargs = {"storage_path": os.path.join(batch_dir, "used_subjects.json")}

    results = []
    for i in range(1, count + 1):
        story_dir = os.path.join(batch_dir, f"story_{i:02d}")
        os.makedirs(story_dir, exist_ok=True)

        print(f"[{brand_id}] Generating story {i}/{count}...")
        result = run_brand(
            brand_id=brand_id,
            brands_root=brands_root,
            db_path=os.path.join(story_dir, "log.db"),
            force_dry_run=True,
            dedup_kwargs=batch_dedup_kwargs,
        )

        # Copy everything the run actually produced (images, rendered
        # frames, voice/subtitle files, the final video) straight from
        # its temp work_dir into this story's numbered folder.
        work_dir = result["work_dir"]
        for name in os.listdir(work_dir):
            src = os.path.join(work_dir, name)
            dst = os.path.join(story_dir, name)
            if os.path.isfile(src):
                shutil.copy2(src, dst)

        story = result["story"]
        with open(os.path.join(story_dir, "story.json"), "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(story), f, indent=2, ensure_ascii=False)

        with open(os.path.join(story_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump({
                "brand_id": brand_id,
                "index": i,
                "count": count,
                "timestamp": timestamp,
                "title": story.title,
                "tts_provider_used": result["tts_used"],
                "publish_mode": "dry_run (forced -- --count never publishes)",
            }, f, indent=2, ensure_ascii=False)

        print(f"[{brand_id}] story {i}/{count} saved -> {story_dir}")
        results.append({"story_dir": story_dir, "title": story.title})

    print(f"[{brand_id}] {count} stories generated in {batch_dir}")
    return results