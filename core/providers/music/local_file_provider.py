"""
core/providers/music/local_file_provider.py

Fully generic: no default file path baked in. The provider's only
responsibility is to verify/access whatever path it's given and
return it if it exists, or None if not (a safe, generic "no music"
state that build_video() already handles as valid). Which file, if
any, is entirely brand config (`music.local_file` in config.yaml),
injected by run.py -- the same mechanism-vs-content split used
everywhere else (font path, watermark text, image style suffix, voice
profiles).
"""
import os
from .base import MusicProvider


class LocalFileMusicProvider(MusicProvider):
    def __init__(self, file_path: str):
        self.file_path = file_path

    def generate(self, *args, **kwargs) -> str:
        if self.file_path and os.path.exists(self.file_path):
            return os.path.abspath(self.file_path)
        return None
