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
                    fallback_provider=None):
    """
    llm_provider: core.providers.llm.base.LLMProvider
    system_prompt / user_prompt: raw strings, brand-owned content
    parser: core.story.parser_base.StoryParser, brand-owned
    fallback_provider: core.story.fallback_base.FallbackProvider,
        brand-owned. If generation raises OR produces an incomplete
        Story, this is used instead. If None, failures propagate to
        the caller (useful for brands that haven't defined a fallback
        yet, or for tests).
    """
    try:
        raw_text = llm_provider.generate(system_prompt, user_prompt, temperature, max_tokens)
        story = parser.parse(raw_text)
        if _is_valid(story):
            return story
    except Exception:
        pass

    if fallback_provider is not None:
        return fallback_provider.get_fallback_story()

    raise Exception("Story generation failed and no fallback_provider was supplied.")
