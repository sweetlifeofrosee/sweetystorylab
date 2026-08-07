"""
core/pipeline/run.py

The orchestrator. This is the one module that knows the *sequence* of
stages -- but never their *content*. It loads a brand by id, resolves
that brand's own prompt files + parser + config, and drives the
generic providers/renderers. No brand_id branching anywhere below.
"""
import importlib
import json
import os
import tempfile

from ..config.loader import load_brand_config
from ..config import platform as platform_config
from ..story.engine import generate_story
from ..renderers.registry import render_segment, get_spec
from ..renderers import layout_profiles
from ..providers.llm.groq_provider import GroqProvider
from ..providers.image.pollinations_provider import PollinationsProvider
from ..providers.tts.edge_tts_provider import EdgeTTSProvider
from ..providers.tts.elevenlabs_provider import ElevenLabsProvider
from ..providers.tts.orchestrator import generate_voice
from ..subtitles.beat_splitter import rewrite_srt_as_beats
from ..providers.music.local_file_provider import LocalFileMusicProvider
from ..providers.publish.facebook_provider import FacebookReelsProvider
from ..providers.publish.tiktok_provider import TikTokProvider
from ..providers.publish.base import PublishResult
from ..video.assembler import build_video
from ..storage.log_store import init_db, log_result


class RenderContext:
    """Passed to every renderer -- see core/renderers/*. Carries brand
    styling so renderers stay generic across brands."""
    def __init__(self, work_dir, title, watermark_text, font_path,
                 total_narration_scenes, question_max_font_size=None,
                 question_text_color=None, layout_profile=None):
        self.work_dir = work_dir
        self.title = title
        self.watermark_text = watermark_text
        self.font_path = font_path
        self.total_narration_scenes = total_narration_scenes
        self.question_max_font_size = question_max_font_size
        self.question_text_color = question_text_color
        # Platform Layout Profile (see core/renderers/layout_profiles.py).
        # Defaults to Facebook -- every existing caller that doesn't pass
        # this argument keeps producing identical output to before.
        self.layout_profile = layout_profile or layout_profiles.FACEBOOK
        self.image_path = None  # set per-segment before rendering
        self.scene_index = 0    # set per-segment before rendering


# Overridable via env var so a workflow step (or a test) can point
# this somewhere else without run_brand() needing a new parameter.
# Deliberately NOT under work_dir/output_root -- those are
# per-run/per-story and often cleaned up or archived; this needs to
# survive to a step that runs after run_brand() returns, so it
# defaults to the repo/working directory root instead.
_TIKTOK_REFRESHED_CREDENTIALS_PATH_ENV = "TIKTOK_REFRESHED_CREDENTIALS_PATH"
_TIKTOK_REFRESHED_CREDENTIALS_DEFAULT_PATH = ".tiktok_refreshed_credentials.json"


def _persist_refreshed_tiktok_credentials(publish_result: PublishResult, brand_id: str) -> None:
    """
    Writes publish_result.refreshed_credentials to a local, gitignored
    JSON file if present -- a no-op otherwise (dry run, or a publish
    attempt that failed before ever reaching the refresh step).

    Deliberately does NOT talk to GitHub's API, an external secrets
    manager, or anything else "where credentials actually live
    long-term" -- that decision was explicitly left to a separate
    workflow step/helper (see tiktok_auth.py's module docstring for
    the same boundary applied one layer down). This function's only
    job is: don't let a successfully-refreshed token pair evaporate
    when the process exits, by putting it somewhere a follow-up step
    can find it.

    Never logs the actual token values -- only the fact that a file
    was written and where, so CI logs stay clean.
    """
    if publish_result.refreshed_credentials is None:
        return

    path = os.environ.get(
        _TIKTOK_REFRESHED_CREDENTIALS_PATH_ENV,
        _TIKTOK_REFRESHED_CREDENTIALS_DEFAULT_PATH,
    )
    payload = {
        "brand_id": brand_id,
        **publish_result.refreshed_credentials,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    print(
        f"[{brand_id}] TikTok credentials were refreshed during this run. "
        f"New token pair written to {path} (not committed -- see .gitignore) "
        f"for a follow-up step to persist. This file is NOT deleted by "
        f"run_brand() itself -- whatever reads it is responsible for "
        f"removing it once persisted."
    )


def run_brand(brand_id: str, brands_root: str = "brands", db_path: str = "posts.db",
              force_dry_run: bool = False, dedup_kwargs: dict = None,
              platform: str = "facebook"):
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
    (the canonical, production file).

    platform: which Platform Layout Profile (core/renderers/
    layout_profiles.py) to render with -- "facebook" (default) or
    "tiktok". This ONLY changes rendering geometry (title/watermark/
    question-slide sizing+position, subtitle margin). It does not
    touch prompts, story generation, images, music, voice, or timing.

    Publishing: platform="facebook" (the default) is completely
    unchanged -- every existing call site behaves exactly as before.
    platform="tiktok" now actually publishes via TikTokProvider (Phase
    2) instead of rendering-and-skipping -- see TikTokProvider's own
    docstring for the refresh/creator_info/chunked-upload/poll flow.
    Any OTHER platform value keeps the old render-and-skip placeholder
    behavior, so a platform added later without its own provider yet
    doesn't crash -- it degrades the same way tiktok itself used to.

    TikTok credential rotation: TikTokProvider.publish() may return a
    freshly-rotated (access_token, refresh_token) pair in
    publish_result.refreshed_credentials -- TikTok invalidates the old
    refresh_token on every use, so this is not optional to discard.
    Per the storage-agnostic design agreed for tiktok_auth.py/
    tiktok_provider.py, run_brand() itself does not call any
    GitHub-specific API to persist it -- it writes it to a local JSON
    file instead (see TIKTOK_REFRESHED_CREDENTIALS_PATH below) and
    leaves picking it up and persisting it (repo secret update,
    external secrets manager, etc.) to a separate step. The file is
    NOT committed (see .gitignore) and its path is deliberately
    configurable via env var so a workflow step can locate it without
    run_brand() needing to know anything about where it's running."""
    layout_profile = layout_profiles.get_profile(platform)

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
            layout_profile=layout_profile,
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

    # Phase 1 subtitle beat-splitting (see design conversation): purely
    # a post-processing pass on the .srt file generate_voice() already
    # produced, regardless of which TTS path made it. Does not touch
    # voice_path, does not touch either TTS provider, does not touch
    # narration text. Writes a second file rather than overwriting
    # srt_path, so the original TTS-provider output is preserved on
    # disk for debugging/comparison if beat lengths ever need tuning.
    beats_srt_path = os.path.join(work_dir, "voice_beats.srt")
    rewrite_srt_as_beats(srt_path, beats_srt_path,
                          max_chars=layout_profile.subtitle_beat_max_chars)

    music_local_path = (
        os.path.join(brand_dir, config.music_local_file)
        if config.music_local_file else None
    )
    music_provider = LocalFileMusicProvider(file_path=music_local_path)
    music_path = music_provider.generate()

    output_path = os.path.join(work_dir, "final.mp4")
    build_video(rendered_segments, voice_path, beats_srt_path, work_dir, output_path, music_path,
                layout_profile=layout_profile)

    # CORRECTED (architecture review): real post.py uses
    # f"{caption}\n\n{hashtags}" -- this previously used a single
    # space, never verified until now. Real parity, not a style choice.
    caption = f"{story.caption}\n\n{' '.join(story.hashtags)}"

    if platform == "facebook":
        publisher = FacebookReelsProvider(
            page_id=config.facebook.page_id,
            access_token=config.facebook.access_token,
            is_dry_run=(config.facebook.is_dry_run or force_dry_run),
        )
        publish_result = publisher.publish(output_path, story.title, caption)
    elif platform == "tiktok":
        tiktok_client_key = platform_config.get_tiktok_client_key()
        tiktok_client_secret = platform_config.get_tiktok_client_secret()
        # Real dry-run state combines brand-level (refresh_token) and
        # platform-level (client_key/client_secret) missing pieces --
        # TikTokConfig.is_dry_run alone only knows about the brand
        # side (see TikTokConfig's docstring in core/config/loader.py).
        tiktok_is_dry_run = (
            config.tiktok.is_dry_run
            or not tiktok_client_key
            or not tiktok_client_secret
            or force_dry_run
        )
        publisher = TikTokProvider(
            client_key=tiktok_client_key,
            client_secret=tiktok_client_secret,
            refresh_token=config.tiktok.refresh_token,
            is_dry_run=tiktok_is_dry_run,
        )
        publish_result = publisher.publish(output_path, story.title, caption)
        _persist_refreshed_tiktok_credentials(publish_result, brand_id)
    else:
        # Placeholder path for any platform value that isn't facebook
        # or tiktok -- kept so a future --platform without its own
        # provider yet degrades safely instead of crashing, the same
        # way tiktok itself used to before this phase. Deliberately
        # does NOT call FacebookReelsProvider -- publishing a
        # tiktok-profile video to Facebook would be wrong, and the
        # real Facebook publish path (above) is completely untouched.
        publish_result = PublishResult(
            success=True,
            dry_run=False,
            detail=(
                f"Rendered for platform='{platform}' -- no automated upload "
                f"configured for this platform yet. Video is ready at "
                f"{output_path} for manual upload."
            ),
        )

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
        "beats_srt_path": beats_srt_path,
    }


def run_brand_batch(brand_id: str, count: int, brands_root: str = "brands",
                     output_root: str = "output", platform: str = "facebook"):
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

    platform: same Platform Layout Profile selector as run_brand()
    (default "facebook", so existing --count usage is unaffected).
    Useful for generating a batch of TikTok-profile videos to review
    before wider use, without publishing anything either way.
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
            platform=platform,
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
                "platform": platform,
                "publish_mode": "dry_run (forced -- --count never publishes)",
            }, f, indent=2, ensure_ascii=False)

        print(f"[{brand_id}] story {i}/{count} saved -> {story_dir}")
        results.append({"story_dir": story_dir, "title": story.title})

    print(f"[{brand_id}] {count} stories generated in {batch_dir}")
    return results