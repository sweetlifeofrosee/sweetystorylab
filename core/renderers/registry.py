"""
core/renderers/registry.py

This is the enforcement point for "arbitrary ordered segments, not
arbitrary behavior" (see architecture discussion). Brands compose
stories from this closed set of segment types via their
`segment_template` config. Core code never branches on brand_id or
genre -- it only ever branches on segment `type`, dispatching through
this registry.

Adding a new segment type is a deliberate, rare, core-level change --
made only when a real brand demonstrates a rendering need that no
existing type covers. It is NOT something a brand can invent on its
own by editing YAML.

Each registered type provides:
  - content_fields: what this segment type requires to be considered
                     complete (consumed by core/story/engine.py's
                     generic fallback-validity check -- NOT used to
                     build an LLM generation schema; that approach was
                     considered and deliberately rejected in favor of
                     keeping parsing entirely brand-owned)
  - defaults: has_voiceover / duration_mode defaults for this type
  - render: a function (segment, ctx) -> frame_path that builds the
            visual frame for one segment. `ctx` carries brand-level
            styling (watermark_text, font_path) so the renderer stays
            generic across brands.
"""
from . import narration_scene, question_slide

SEGMENT_TYPES = {
    "narration_scene": {
        "content_fields": ["narration", "image_prompt"],
        "defaults": {"has_voiceover": True, "duration_mode": "audio_length"},
        "render": narration_scene.render,
    },
    "question_slide": {
        "content_fields": ["text"],
        "defaults": {"has_voiceover": False, "duration_mode": "fixed",
                      "duration_seconds": 4.0},
        "render": question_slide.render,
    },
}


def get_spec(segment_type: str) -> dict:
    if segment_type not in SEGMENT_TYPES:
        raise ValueError(
            f"Unknown segment type '{segment_type}'. Registered types: "
            f"{list(SEGMENT_TYPES.keys())}. New types are added to "
            f"core/renderers/, not invented per-brand."
        )
    return SEGMENT_TYPES[segment_type]


def render_segment(segment, ctx) -> str:
    spec = get_spec(segment.type)
    return spec["render"](segment, ctx)
