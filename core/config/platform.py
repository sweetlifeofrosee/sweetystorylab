"""
core/config/platform.py

Platform-level secrets/config: infrastructure shared across every
brand today (Groq, ElevenLabs). This is deliberately separate from
brands/*/config.yaml, which holds brand-owned IDENTITY (Facebook Page,
prompts, branding) -- credentials that vary per brand by definition.

Architecture decision (recorded here, not just in conversation):
Groq and ElevenLabs are ONE shared account across the whole platform
today. If a brand ever needs its own account, move that specific
credential to brand config using the same `*_env` reference pattern
Facebook already uses (core/config/loader.py) -- don't move everything
here preemptively just because one brand needed an exception.
"""
import os


class PlatformConfigError(Exception):
    """Raised when a required platform-level secret is missing."""


def get_groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise PlatformConfigError(
            "GROQ_API_KEY is not set. This is platform infrastructure, "
            "shared by every brand -- check your GitHub Actions secrets, "
            "not brand config.yaml."
        )
    return key


def get_elevenlabs_api_key():
    """Optional: brands can run on Edge TTS alone if this is unset --
    the TTS fallback chain already handles that (see
    core/providers/tts/orchestrator.py)."""
    return os.environ.get("ELEVENLABS_API_KEY")
