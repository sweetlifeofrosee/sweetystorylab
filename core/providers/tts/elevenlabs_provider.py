"""
core/providers/tts/elevenlabs_provider.py

Direct port of the original post.py `generate_voice_elevenlabs()`.
`preferred_voices` list is brand config (`voice.elevenlabs_preferred`),
matching the earlier design decision -- this was already agreed as a
config field, not a new change made here.
"""
import requests
from .base import TTSProvider


class ElevenLabsProvider(TTSProvider):
    def __init__(self, api_key: str, preferred_voices: list):
        self.api_key = api_key
        self.preferred_voices = preferred_voices

    def _resolve_voice_id(self):
        voices_res = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": self.api_key},
            timeout=10,
        )
        voices = voices_res.json().get("voices", [])
        for name in self.preferred_voices:
            match = next((v for v in voices if v["name"] == name), None)
            if match:
                return match["voice_id"]
        if voices:
            return voices[0]["voice_id"]
        return None

    def generate(self, text: str, voice_file: str) -> bool:
        try:
            voice_id = self._resolve_voice_id()
        except Exception:
            return False
        if not voice_id:
            return False

        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
                "style": 0.5,
                "use_speaker_boost": True,
            },
        }
        try:
            res = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers=headers, json=payload, timeout=60,
            )
            if res.status_code == 429:
                return False  # quota exceeded -> caller falls back
            res.raise_for_status()
            with open(voice_file, "wb") as f:
                f.write(res.content)
            return True
        except Exception:
            return False
