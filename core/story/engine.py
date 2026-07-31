"""
core/story/engine.py

Orchestration + resilience. Still knows nothing about prompt formats,
field names, or scene counts -- that stays entirely inside the brand's
StoryParser. What this file DOES own, deliberately, per architecture
decision: the generic "try generation, validate, fall back" mechanism.
That's pipeline resilience, not brand behavior -- every brand will
eventually want it, and it doesn't require knowing anything about
genre content to implement.

Validity checking is generic too: it consults the renderer registry
for each segment's required content_fields (already defined there for
documentation purposes) and checks they're populated. This replicates
the real post.py's `all(s["narration"] for s in scenes)` check, but
generalized to any segment_template instead of hardcoded to 3 scenes.

DEDUPLICATION (additive, optional): a brand may supply a
`dedup_checker` object exposing two methods:
  - is_acceptable(story) -> bool
  - retry_hint(story) -> str   (short text appended to the prompt on retry)
If dedup_checker is None (the default -- e.g. Horror Lab today), this
is a complete no-op: behavior is byte-identical to before this
capability existed, exactly one generation attempt. Only brands that
explicitly opt in (via content.dedup_module in config.yaml) pay for
the bounded retry loop.
"""
from ..renderers.registry import get_spec


def _is_valid(story) -> bool:
    if not story.segments:
        return False
    for segment in story.segments:
        spec = get_spec(segment.type)
        for field_name in spec["content_fields"]:
            if not getattr(segment, field_name, None):
                return False
    return True


def generate_story(llm_provider, system_prompt: str, user_prompt: str,
                    parser, temperature: float, max_tokens: int,
                    fallback_provider=None, dedup_checker=None,
                    max_regeneration_attempts: int = 2):
    """
    llm_provider: core.providers.llm.base.LLMProvider
    system_prompt / user_prompt: raw strings, brand-owned content
    parser: core.story.parser_base.StoryParser, brand-owned
    fallback_provider: core.story.fallback_base.FallbackProvider,
        brand-owned. Used if generation raises, produces an invalid
        Story, or (if dedup_checker is set) every regeneration attempt
        is rejected as a duplicate.
    dedup_checker: optional, brand-owned. If provided, a successfully
        parsed and structurally-valid Story is additionally checked via
        dedup_checker.is_acceptable(story). If rejected, the story is
        regenerated (up to max_regeneration_attempts additional tries),
        with dedup_checker.retry_hint(story) appended to the prompt
        each time to steer the model away from the rejected subject.
    """
    attempts_remaining = 1 + (max_regeneration_attempts if dedup_checker else 0)
    current_user_prompt = user_prompt

    while attempts_remaining > 0:
        attempts_remaining -= 1
        try:
            raw_text = llm_provider.generate(system_prompt, current_user_prompt, temperature, max_tokens)
            story = parser.parse(raw_text)
            if _is_valid(story):
                if dedup_checker is None or dedup_checker.is_acceptable(story):
                    return story
                if attempts_remaining > 0:
                    current_user_prompt = user_prompt + "\n\n" + dedup_checker.retry_hint(story)
                continue
        except Exception:
            pass

    if fallback_provider is not None:
        return fallback_provider.get_fallback_story()

    raise Exception("Story generation failed and no fallback_provider was supplied.")