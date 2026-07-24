"""
core/providers/tts/orchestrator.py

Direct port of the original post.py `generate_voice()`,
`generate_srt_from_voice()`, and `vtt_to_srt()`. Pure mechanics --
no genre-specific content anywhere in this file, so nothing here
needed flagging in the audit.
"""
import json
import re
import subprocess


def generate_voice(text: str, voice_file: str, srt_file: str,
                    primary_provider=None, fallback_provider=None) -> str:
    """Try primary_provider (e.g. ElevenLabs) first if given, fall back
    to fallback_provider (e.g. Edge TTS). Always produces voice_file +
    srt_file. Returns which provider was actually used, for logging."""
    clean = text.replace("#", "").replace("\U0001F47B", "").replace("...", ". ").strip()

    used_primary = False
    if primary_provider is not None:
        used_primary = primary_provider.generate(clean, voice_file)

    if used_primary:
        generate_srt_from_voice(clean, voice_file, srt_file)
        return "primary"
    else:
        fallback_provider.generate(clean, voice_file)
        vtt_file = voice_file.replace(".mp3", ".vtt")
        vtt_to_srt(vtt_file, srt_file)
        return "fallback"


def generate_srt_from_voice(text: str, voice_file: str, srt_file: str):
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", voice_file],
        capture_output=True, text=True,
    )
    duration = float(json.loads(probe.stdout)["streams"][0]["duration"])

    words = text.split()
    total_words = len(words)
    time_per_word = duration / total_words if total_words > 0 else 0.4

    srt_blocks = []
    counter = 1
    chunk_size = 3

    def fmt(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    for i in range(0, total_words, chunk_size):
        chunk = words[i:i + chunk_size]
        start_time = i * time_per_word
        end_time = min((i + chunk_size) * time_per_word, duration)
        block = f"{counter}\n{fmt(start_time)} --> {fmt(end_time)}\n{' '.join(chunk)}"
        srt_blocks.append(block)
        counter += 1

    with open(srt_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(srt_blocks))


def vtt_to_srt(vtt_path: str, srt_path: str):
    with open(vtt_path, "r", encoding="utf-8") as f:
        raw = f.read()

    raw = re.sub(r"WEBVTT\n", "", raw)
    raw = re.sub(r"NOTE[^\n]*\n[^\n]*\n", "", raw)

    blocks = raw.strip().split("\n\n")
    srt_out = []
    counter = 1

    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        timing_line = next((l for l in lines if "-->" in l), None)
        if not timing_line:
            continue

        timing = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", timing_line)
        timing = re.sub(r"\s+(align|position|line|size):\S+", "", timing).strip()

        text_lines = [l for l in lines if "-->" not in l]
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text).strip()
        text = re.sub(r"^\d+[\s\.]+", "", text).strip()

        if text:
            srt_out.append(f"{counter}\n{timing}\n{text}")
            counter += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(srt_out))
