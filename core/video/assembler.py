"""
core/video/assembler.py

Direct port of the original post.py `build_video()`. Pure mechanics --
no genre-specific content. The one necessary generalization: the
original computed `scene_duration = total_duration / 3`, hardcoding a
3-scene assumption. This version divides audio duration across
whichever segments actually have `duration_mode="audio_length"`, and
uses each segment's own `duration_seconds` for fixed-duration segments
(e.g. question_slide).

SUBTITLE STYLING (Direction A + C, generic across both brands):
  - Lighter recipe: thinner outline, lighter shadow, no bold, slightly
    larger font, more margin from the bottom edge -- replacing the
    previous heavy "meme subtitle" look (Outline=3, Shadow=2, Bold=1).
  - A soft, restrained bottom gradient (generated once per video, pure
    black fading in from transparent) sits behind the caption text
    instead of relying on outline weight for legibility -- captions
    read as emerging from the image, not sitting inside a container.
  - This required unifying the video processing into a single
    -filter_complex (overlay the gradient, then burn subtitles on top)
    instead of the previous -vf/-filter_complex mix -- an internal
    robustness improvement, not a public interface change; build_video()'s
    signature and behavior are otherwise unchanged.

PLATFORM LAYOUT PROFILES: subtitle_target_margin_px now comes from a
LayoutProfile (see core/renderers/layout_profiles.py) instead of a
hardcoded module constant, so a platform's caption/UI overlay can be
cleared without touching subtitle content, timing, or styling.
Facebook's profile value (150) equals the original hardcoded constant,
so build_video(..., layout_profile=None) -- or the explicit Facebook
profile -- produces byte-identical output to before this change.
"""
import json
import os
import subprocess
from PIL import Image, ImageDraw
from ..renderers.layout_profiles import FACEBOOK as _DEFAULT_PROFILE

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SUBTITLE_GRADIENT_HEIGHT = 460     # how tall the soft bottom darkening region is
SUBTITLE_GRADIENT_MAX_ALPHA = 190  # darkest point, at the very bottom edge
SUBTITLE_GRADIENT_EASE = 1.6       # >1 keeps the top of the gradient nearly invisible,
                                    # concentrating the darkening near the bottom edge

# EMPIRICAL CALIBRATION -- not a documented pixel mapping.
#
# FFmpeg's `subtitles` filter, when given a plain .srt, converts it to
# ASS internally using its own default script resolution (commonly
# 384x288 in libass), NOT the actual output video resolution. This
# means MarginV in force_style is NOT literal pixels -- it's scaled by
# (actual_output_height / assumed_script_height).
#
# We tried the documented fix for this (the `original_size` filter
# option) and measured, by rendering real frames and locating the
# actual subtitle pixel position, that it had ZERO effect on this
# scaling behavior for auto-converted .srt input -- `original_size` is
# documented as an aspect-ratio/font-scaling aid, not script-resolution
# override, and doesn't apply to this code path.
#
# Rather than build real .ass-file generation/rewriting infrastructure
# to force a literal PlayResY, we measured the actual scale factor
# directly: MarginV=110 produced text 749px from the bottom edge of a
# real 1920px-tall rendered frame; MarginV=120 produced 816px. Both
# measurements give the same ratio, ~6.8x. If a future FFmpeg/libass
# version changes this default, recalibrate this one constant by
# rendering a test frame and measuring the actual text position the
# same way (see the verification method used when this was derived).
# This scale factor itself is a libass/FFmpeg implementation detail,
# not a platform concern -- it stays a module constant for every
# platform; only the *target* margin (how far up the platform needs
# the text to sit) varies, via LayoutProfile.
LIBASS_MARGINV_SCALE_FACTOR = 6.8


def _generate_subtitle_gradient(work_dir: str) -> str:
    """A soft, generic bottom gradient (transparent -> darkened black)
    that supports subtitle legibility without a visible panel/box.
    Same treatment for every brand -- purely tonal, no brand styling."""
    grad = Image.new("RGBA", (CANVAS_WIDTH, SUBTITLE_GRADIENT_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(grad)
    for y in range(SUBTITLE_GRADIENT_HEIGHT):
        progress = y / SUBTITLE_GRADIENT_HEIGHT
        alpha = int((progress ** SUBTITLE_GRADIENT_EASE) * SUBTITLE_GRADIENT_MAX_ALPHA)
        draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(0, 0, 0, alpha))
    path = f"{work_dir}/subtitle_gradient.png"
    grad.save(path, "PNG")
    return path


def build_video(rendered_segments, voice_path: str, srt_path: str,
                 work_dir: str, output_path: str, music_path: str = None,
                 layout_profile=None) -> str:
    """
    rendered_segments: list of (frame_path, segment) tuples, in order.
        segment.duration_mode == "audio_length" segments split the
        narration audio's total duration evenly among themselves.
        segment.duration_mode == "fixed" segments use their own
        duration_seconds.

    layout_profile: a core.renderers.layout_profiles.LayoutProfile.
        Defaults to the Facebook profile (the historical hardcoded
        margin), so every existing caller that doesn't pass this
        argument is completely unaffected.
    """
    profile = layout_profile or _DEFAULT_PROFILE
    subtitle_margin_v = round(profile.subtitle_target_margin_px / LIBASS_MARGINV_SCALE_FACTOR)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", voice_path],
        capture_output=True, text=True,
    )
    total_duration = float(json.loads(probe.stdout)["streams"][0]["duration"])

    audio_length_segments = [s for _, s in rendered_segments if s.duration_mode == "audio_length"]
    per_scene_duration = (
        total_duration / len(audio_length_segments) if audio_length_segments else total_duration
    )

    scene_frames = []
    fixed_total = 0.0
    for frame_path, segment in rendered_segments:
        if segment.duration_mode == "fixed":
            duration = segment.duration_seconds or 4.0
            fixed_total += duration
        else:
            duration = per_scene_duration
        scene_frames.append((frame_path, duration))

    concat_file = f"{work_dir}/concat.txt"
    with open(concat_file, "w") as f:
        for frame_path, duration in scene_frames:
            f.write(f"file '{frame_path}'\n")
            f.write(f"duration {duration:.3f}\n")
        f.write(f"file '{scene_frames[-1][0]}'\n")

    temp_video = f"{work_dir}/temp_video.mp4"
    padded_voice = f"{work_dir}/voice_padded.mp3"

    pad_result = subprocess.run([
        "ffmpeg", "-y", "-i", voice_path,
        "-af", f"apad=pad_dur={fixed_total}",
        "-codec:a", "libmp3lame", "-q:a", "2",
        padded_voice,
    ], capture_output=True)
    if pad_result.returncode != 0:
        padded_voice = voice_path

    num_frames = len(scene_frames)
    fade_duration = 0.8

    if num_frames == 1:
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", scene_frames[0][0],
            "-t", str(scene_frames[0][1]),
            "-vf", "scale=1080:1920,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            temp_video,
        ], check=True, capture_output=True)
    else:
        inputs = []
        for frame_path, duration in scene_frames:
            inputs += ["-loop", "1", "-t", str(duration + fade_duration), "-i", frame_path]

        filter_parts = []
        cumulative = 0.0
        prev_label = "[0:v]"
        for i in range(1, num_frames):
            cumulative += scene_frames[i - 1][1]
            offset = max(0.1, cumulative - fade_duration)
            out_label = f"[fade{i}]" if i < num_frames - 1 else ""
            filter_parts.append(
                f"{prev_label}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}{out_label}"
            )
            prev_label = f"[fade{i}]"
        filter_complex = ",".join(filter_parts) if len(filter_parts) == 1 else ";".join(filter_parts)
        filter_complex += ",scale=1080:1920,fps=30"

        result = subprocess.run([
            "ffmpeg", "-y",
        ] + inputs + [
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", "30", temp_video,
        ], capture_output=True, text=True)

        if result.returncode != 0:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-vf", "scale=1080:1920,fps=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-r", "30", temp_video,
            ], check=True, capture_output=True)

    gradient_path = _generate_subtitle_gradient(work_dir)
    overlay_y = CANVAS_HEIGHT - SUBTITLE_GRADIENT_HEIGHT
    video_duration = total_duration + fixed_total  # matches padded_voice's actual length

    # Direction A: lighter subtitle recipe -- thinner outline, lighter
    # shadow, no bold, slightly larger font, more breathing room from
    # the bottom edge. Legibility now comes from the soft gradient
    # (Direction C) instead of a heavy outline.
    #
    # MarginL/MarginR are only appended when the profile sets them
    # (nonzero) -- Facebook's profile has both at 0, so its style
    # string below is byte-identical to before this platform-aware
    # version existed. See core/renderers/layout_profiles.py for how
    # subtitle_font_size / subtitle_margin_l / subtitle_margin_r were
    # derived (measured against real rendered frames, not just
    # calculated from style-value ratios).
    style_parts = [
        "FontName=Arial",
        f"FontSize={profile.subtitle_font_size}",
        "PrimaryColour=&H00FFFFFF",
        "OutlineColour=&H00000000",
        "BackColour=&H60000000",
        "Bold=0",
        "Outline=1",
        "Shadow=1",
        "Alignment=2",
        f"MarginV={subtitle_margin_v}",
    ]
    if profile.subtitle_margin_l:
        style_parts.append(f"MarginL={profile.subtitle_margin_l}")
    if profile.subtitle_margin_r:
        style_parts.append(f"MarginR={profile.subtitle_margin_r}")
    subtitle_style = ",".join(style_parts)

    has_music = music_path is not None and os.path.exists(music_path)
    if has_music:
        filter_complex = (
            f"[0:v][1:v]overlay=0:{overlay_y}[bgv];"
            f"[bgv]subtitles={os.path.basename(srt_path)}:force_style='{subtitle_style}'[vout];"
            f"[2:a][3:a]amix=inputs=2:weights=1 0.15:duration=first:normalize=0[aout]"
        )
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-loop", "1", "-t", str(video_duration), "-i", gradient_path,
            "-i", padded_voice,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, text=True, timeout=180, cwd=work_dir)
    else:
        filter_complex = (
            f"[0:v][1:v]overlay=0:{overlay_y}[bgv];"
            f"[bgv]subtitles={os.path.basename(srt_path)}:force_style='{subtitle_style}'[vout]"
        )
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-loop", "1", "-t", str(video_duration), "-i", gradient_path,
            "-i", padded_voice,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "2:a",
            "-c:v", "libx264",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, text=True, timeout=180, cwd=work_dir)

    if result.returncode != 0:
        raise Exception(f"FFmpeg final failed: {result.stderr[-500:]}")

    return output_path