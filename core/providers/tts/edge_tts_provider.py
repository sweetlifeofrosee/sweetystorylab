"""
core/providers/tts/edge_tts_provider.py

Direct port of the original post.py `generate_voice_edgetts()`.
Voice name is brand config (matches your earlier design decision --
`voice.edge_tts_voice` in config.yaml), not hardcoded.
"""
import subprocess
from .base import TTSProvider


class EdgeTTSProvider(TTSProvider):
    def __init__(self, voice: str, rate: str = "-10%"):
        self.voice = voice
        self.rate = rate

    def generate(self, text: str, voice_file: str) -> bool:
        result = subprocess.run(
            [
                "edge-tts",
                "--voice", self.voice,
                f"--rate={self.rate}",
                "--text", text,
                "--write-media", voice_file,
                "--write-subtitles", voice_file.replace(".mp3", ".vtt"),
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise Exception(f"Edge TTS failed: {result.stderr}")
        return True
