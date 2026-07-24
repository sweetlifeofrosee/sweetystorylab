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
                 total_narration_scenes):
        self.work_dir = work_dir
        self.title = title
        self.watermark_text = watermark_text
        self.font_path = font_path
        self.total_narration_scenes = total_narration_scenes
        self.image_path = None  # set per-segment before rendering
        self.scene_index = 0    # set per-segment before rendering


def run_brand(brand_id: str, brands_root: str = "brands", db_path: str = "posts.db"):
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

    llm = GroqProvider(api_key=platform_config.get_groq_api_key(), model=config.llm_model)
    story = generate_story(llm, system_prompt, user_prompt, parser,
                            fallback_provider=fallback_provider,
                            temperature=config.llm_temperature,
                            max_tokens=config.llm_max_tokens)

    work_dir = tempfile.mkdtemp(prefix=f"{brand_id}_")
    font_path = os.path.join(brand_dir, config.font_file)

    narration_scene_count = sum(
        1 for s in story.segments if get_spec(s.type)["defaults"]["duration_mode"] == "audio_length"
    )

    image_provider = PollinationsProvider(style_suffix=config.image_style_suffix,
                                           fallback_dir=config.image_fallback_dir)
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
        is_dry_run=config.facebook.is_dry_run,
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
    }
