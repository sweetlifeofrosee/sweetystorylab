"""
core/video/assembler.py

Direct port of the original post.py `build_video()`. Pure mechanics --
no genre-specific content. The one necessary generalization: the
original computed `scene_duration = total_duration / 3`, hardcoding a
3-scene assumption. This version divides audio duration across
whichever segments actually have `duration_mode="audio_length"`, and
uses each segment's own `duration_seconds` for fixed-duration segments
(e.g. question_slide).

This generalization is REQUIRED for the assembler to work with any
segment_template at all -- it's not a stylistic choice, and for
Horror Lab's exact 3-scene + 1 fixed-question shape it reproduces
identical timing (total_duration / 3 per scene, 4s fixed for the
question slide) to the original.
"""
import json
import os
import subprocess


def build_video(rendered_segments, voice_path: str, srt_path: str,
                 work_dir: str, output_path: str, music_path: str = None) -> str:
    """
    rendered_segments: list of (frame_path, segment) tuples, in order.
        segment.duration_mode == "audio_length" segments split the
        narration audio's total duration evenly among themselves.
        segment.duration_mode == "fixed" segments use their own
        duration_seconds.
    """
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

    subtitle_style = (
        "FontName=Arial,"
        "FontSize=9,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H80000000,"
        "Bold=1,"
        "Outline=3,"
        "Shadow=2,"
        "Alignment=2,"
        "MarginV=80"
    )

    has_music = music_path is not None and os.path.exists(music_path)
    if has_music:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-stream_loop", "-1", "-i", music_path,
            "-c:v", "libx264",
            "-vf", f"subtitles={os.path.basename(srt_path)}:force_style='{subtitle_style}'",
            "-filter_complex",
            "[1:a][2:a]amix=inputs=2:weights=1 0.15:duration=first:normalize=0[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, text=True, timeout=180, cwd=work_dir)
    else:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", padded_voice,
            "-c:v", "libx264",
            "-vf", f"subtitles={os.path.basename(srt_path)}:force_style='{subtitle_style}'",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ], capture_output=True, text=True, timeout=180, cwd=work_dir)

    if result.returncode != 0:
        raise Exception(f"FFmpeg final failed: {result.stderr[-500:]}")

    return output_path
