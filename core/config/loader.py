"""
core/config/loader.py

Loads a brand's config.yaml, validates required fields, and resolves
secret REFERENCES (env var names) against the actual environment.

Design rule: brand config files may contain references to secrets
(env var names) but never secret values themselves. This module is the
single place where that resolution happens, so brand code never touches
os.environ directly, and secrets never live in a committed file.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os
import yaml


class ConfigError(Exception):
    """Raised when a brand config is missing required fields."""


@dataclass
class FacebookConfig:
    page_id: Optional[str]
    access_token: Optional[str]
    is_dry_run: bool  # True if credentials are missing/placeholder -> publisher
                       # should log intent instead of calling the real API.


@dataclass
class TikTokConfig:
    # client_key/client_secret are NOT here -- those identify the
    # TikTok developer app, shared across every brand, and live in
    # platform-level env vars (core/config/platform.py), same
    # separation as Groq/ElevenLabs vs Facebook's per-brand page_id.
    refresh_token: Optional[str]
    is_dry_run: bool  # True if refresh_token is missing/placeholder for
                       # this brand -- mirrors FacebookConfig.is_dry_run.
                       # NOTE: does not know about client_key/client_secret
                       # availability -- the caller (run_brand()) combines
                       # this with platform_config.get_tiktok_client_key()/
                       # get_tiktok_client_secret() to decide the real
                       # dry-run state, since those are platform-level,
                       # not brand-level, and this loader only sees brand
                       # config.


@dataclass
class BrandConfig:
    id: str
    name: str
    emoji: str
    parent: Optional[str]

    system_prompt_file: str
    user_prompt_file: str
    parser_module: str  # dotted path to the brand's StoryParser implementation
    fallback_provider_module: str  # dotted path to the brand's FallbackProvider
    dedup_module: Optional[str]    # OPTIONAL -- dotted path to a brand's subject
                                    # deduplication checker. None means no dedup
                                    # (e.g. Horror Lab today) -- not a required field.
    segment_template: list

    voice_profiles: dict          # profile_name -> {edge_tts_voice, elevenlabs_preferred}
    voice_default_profile: str

    llm_model: str
    llm_temperature: float
    llm_max_tokens: int

    music_local_file: Optional[str]
    image_style_suffix: str
    image_fallback_dir: Optional[str]
    image_fallback_color: tuple
    question_max_font_size: int
    question_text_color: tuple

    watermark_text: str
    font_file: str

    schedule_times_pht: list

    facebook: FacebookConfig
    tiktok: TikTokConfig

    raw: dict = field(repr=False, default_factory=dict)
    brand_dir: Path = field(repr=False, default=None)


_REQUIRED_TOP_LEVEL = ["brand", "content", "voice", "branding", "facebook"]


def _resolve_env(var_name):
    if not var_name:
        return None
    return os.environ.get(var_name)


def load_brand_config(brand_dir) -> BrandConfig:
    brand_dir = Path(brand_dir)
    config_path = brand_dir / "config.yaml"
    if not config_path.exists():
        raise ConfigError(f"No config.yaml found in {brand_dir}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise ConfigError(
            f"{config_path}: missing required top-level section(s): {missing}"
        )

    brand = raw["brand"]
    content = raw["content"]
    voice = raw["voice"]
    llm = raw.get("llm", {})
    music = raw.get("music", {})
    image = raw.get("image", {})
    branding = raw["branding"]
    fb = raw["facebook"]
    schedule = raw.get("schedule", {})

    page_id = _resolve_env(fb.get("page_id_env"))
    access_token = _resolve_env(fb.get("access_token_env"))
    is_dry_run = not page_id or not access_token

    facebook_config = FacebookConfig(
        page_id=page_id,
        access_token=access_token,
        is_dry_run=is_dry_run,
    )

    # Optional section -- unlike `facebook`, `tiktok` is NOT in
    # _REQUIRED_TOP_LEVEL. Brands that haven't set up TikTok yet
    # simply get a TikTokConfig with refresh_token=None,
    # is_dry_run=True, same shape as a brand with a real
    # `tiktok:` section but no refresh_token_env resolved -- no
    # separate "TikTok not configured" code path needed anywhere else.
    tk = raw.get("tiktok", {})
    tk_refresh_token = _resolve_env(tk.get("refresh_token_env"))
    tiktok_config = TikTokConfig(
        refresh_token=tk_refresh_token,
        is_dry_run=not tk_refresh_token,
    )

    for required_field in ["segment_template", "system_prompt_file",
                            "user_prompt_file", "parser_module",
                            "fallback_provider_module"]:
        if required_field not in content:
            raise ConfigError(f"{config_path}: content.{required_field} is required")

    if "llm" not in raw or not all(k in raw["llm"] for k in ("model", "temperature", "max_tokens")):
        raise ConfigError(
            f"{config_path}: llm.model, llm.temperature, and llm.max_tokens are "
            f"all required -- no core-level default is provided (a prior version "
            f"of this loader silently defaulted to Horror Lab's real values, "
            f"which was a bug, not a feature)."
        )
    if "font" not in branding:
        raise ConfigError(
            f"{config_path}: branding.font is required -- no core-level default "
            f"is provided, for the same reason as llm.* above."
        )

    voice_profiles = voice.get("profiles", {})
    voice_default_profile = voice.get("default_profile")
    if voice_default_profile and voice_default_profile not in voice_profiles:
        raise ConfigError(
            f"{config_path}: voice.default_profile '{voice_default_profile}' is "
            f"not a key in voice.profiles ({list(voice_profiles.keys())}). "
            f"Failing at config-load time, not silently inside a TTS call later."
        )

    return BrandConfig(
        id=brand["id"],
        name=brand["name"],
        emoji=brand.get("emoji", ""),
        parent=brand.get("parent"),
        system_prompt_file=content["system_prompt_file"],
        user_prompt_file=content["user_prompt_file"],
        parser_module=content["parser_module"],
        fallback_provider_module=content["fallback_provider_module"],
        dedup_module=content.get("dedup_module"),  # optional, no default value needed
        segment_template=content["segment_template"],
        voice_profiles=voice_profiles,
        voice_default_profile=voice_default_profile,
        llm_model=llm["model"],
        llm_temperature=llm["temperature"],
        llm_max_tokens=llm["max_tokens"],
        music_local_file=music.get("local_file"),  # None -> "no music" (safe, generic)
        image_style_suffix=image.get("style_suffix", ""),
        image_fallback_dir=image.get("fallback_dir"),  # None -> fallback image disabled
        image_fallback_color=tuple(image.get("fallback_color", [40, 40, 40])),  # neutral gray, not horror-dark
        # Brand-neutral default (117 -- the value already tuned generically
        # for both brands). A brand overrides this in its own config.yaml
        # to adjust the question slide's visual weight without touching
        # the shared renderer or affecting any other brand.
        question_max_font_size=raw.get("question", {}).get("max_font_size", 117),
        # Brand-neutral default (white). Mystery Lab overrides to its
        # warm gold; Horror Lab keeps white explicitly. Same pattern as
        # question_max_font_size -- config value, not a code branch.
        question_text_color=tuple(raw.get("question", {}).get("text_color", [255, 255, 255])),
        watermark_text=branding.get("watermark_text", brand["name"]),
        font_file=branding["font"],
        schedule_times_pht=schedule.get("times_pht", []),
        facebook=facebook_config,
        tiktok=tiktok_config,
        raw=raw,
        brand_dir=brand_dir,
    )