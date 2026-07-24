"""
core/providers/image/pollinations_provider.py

No hardcoded defaults (architecture review fix): fallback_dir is now
required, sourced entirely from brand config (image.fallback_dir).
If a brand doesn't declare one, None disables the local-fallback-file
step and goes straight to raising -- the caller (run.py) already has
its own final fallback (a plain colored frame) for that case.
"""
import os
import random
import shutil
import time
import requests
from .base import ImageProvider


class PollinationsProvider(ImageProvider):
    def __init__(self, style_suffix: str = "", fallback_dir: str = None):
        self.style_suffix = style_suffix
        self.fallback_dir = fallback_dir

    def generate(self, prompt: str, output_path: str, index: int = 0) -> str:
        full_prompt = f"{prompt}, {self.style_suffix}" if self.style_suffix else prompt
        encoded = requests.utils.quote(full_prompt)
        seed = random.randint(1, 99999)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1080&nologo=true&seed={seed}"
        )

        for attempt in range(3):
            try:
                res = requests.get(url, timeout=90)
                res.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(res.content)
                return output_path
            except Exception:
                if attempt < 2:
                    time.sleep(10)
                    seed = random.randint(1, 99999)
                    url = (
                        f"https://image.pollinations.ai/prompt/{encoded}"
                        f"?width=1080&height=1080&nologo=true&seed={seed}"
                    )

        if self.fallback_dir:
            fallback_path = f"{self.fallback_dir}/fallback_{index}.jpg"
            if os.path.exists(fallback_path):
                shutil.copy(fallback_path, output_path)
                return output_path

        raise Exception("Image generation failed after 3 attempts and no fallback found")

