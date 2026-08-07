"""
core/renderers/question_slide.py

The documentary's closing frame -- designed as an evolution of
narration_scene.py's editorial language, not a separate template.
Shares its wrap/fit algorithm (core/renderers/text_layout.py), its
exact divider element, and its typography/shadow technique. What
makes this frame the emotional climax is emphasis, not a different
layout system:
  - No top brand mark, no scene dots -- both are narration-only
    bookkeeping/identity elements this frame correctly omits, exactly
    as narration_scene.py has neither a "closing" treatment.
  - The question gets a higher font-size ceiling than narration titles
    (more uncontested vertical room, and it's the last thing the
    viewer reads) and is the only gold-colored text in the video.
  - The divider below the question is the SAME element narration
    frames use above their scene dots (identical color/thickness/
    span) -- a deliberate visual callback, not a new motif.
  - Bottom-anchored composition: the question block sits a fixed gap
    above the divider, same spacing philosophy as narration_scene.py's
    title/divider relationship.

Genre-neutral: works for a horror comment-bait question exactly as
well as a documentary closing question -- the text itself is brand/
prompt content, not renderer logic.

Platform selection: `ctx.layout_profile` (see core/renderers/
layout_profiles.py) supplies question_max_text_width,
question_stage_bottom, and question_font_scale. QUESTION_STAGE_TOP is
NOT platform-varying -- 450 already sits well clear of every
platform's top UI, so only the bottom of the stage (closer to
bottom-edge UI like TikTok's caption area) and the width (the
right-side action column) move by platform. Facebook's profile values
reproduce this file's original hardcoded constants exactly.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .text_layout import fit_text, draw_archival_divider
from .layout_profiles import FACEBOOK as _DEFAULT_PROFILE

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

QUESTION_STAGE_TOP = 450         # top of the region the whole group can occupy (moved up 50px)
QUESTION_GROUP_GAP = 40          # gap between the bottom of the question block and the divider
DIVIDER_THICKNESS = 3

QUESTION_MAX_FONT_SIZE = 117     # brand-neutral DEFAULT ceiling (used when RenderContext
                                  # doesn't supply question_max_font_size). Brands override
                                  # via config.yaml's question.max_font_size -- see run.py.
                                  # ceiling (question remains the most dominant text), but
                                  # ~11% smaller for a less cramped, more "luxurious" feel
QUESTION_MIN_FONT_SIZE = 48
QUESTION_FONT_SIZE_STEP = 4
QUESTION_MAX_LINES = 3
QUESTION_LINE_SPACING = 1.15

QUESTION_GOLD = (198, 156, 84)   # brand-neutral DEFAULT (used when RenderContext doesn't
                                  # supply question_text_color). Brands override via
                                  # config.yaml's question.text_color -- see run.py.


def render(segment, ctx) -> str:
    # Defensive fallback, same rationale as narration_scene.py.
    profile = getattr(ctx, "layout_profile", None) or _DEFAULT_PROFILE

    try:
        img = Image.open(ctx.image_path).convert("RGB")
        bg = img.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
        darkener = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0))
        canvas = Image.blend(bg, darkener, 0.65)
    except Exception:
        canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0))

    draw = ImageDraw.Draw(canvas)
    try:
        font_brand = ImageFont.truetype(ctx.font_path, 26)
    except Exception:
        font_brand = ImageFont.load_default()

    stage_height = profile.question_stage_bottom - QUESTION_STAGE_TOP
    max_block_height = stage_height - QUESTION_GROUP_GAP - DIVIDER_THICKNESS
    # Brand-overridable ceiling: falls back to the module default if the
    # caller doesn't provide one via RenderContext (e.g. direct/isolated
    # renderer tests). No brand awareness lives in this file -- it's an
    # opaque value forwarded from config, same pattern as font_path etc.
    # The platform's question_font_scale is then applied on top of
    # whichever ceiling is already in force (brand override or module
    # default) -- 1.0 for Facebook (no change), <1.0 for platforms that
    # need smaller text to fit a tighter safe area. This keeps brand
    # customization intact while still respecting platform constraints.
    brand_max_size = getattr(ctx, "question_max_font_size", None) or QUESTION_MAX_FONT_SIZE
    max_size = round(brand_max_size * profile.question_font_scale)
    lines, font_question, line_height = fit_text(
        draw, segment.text, ctx.font_path,
        max_width=profile.question_max_text_width, max_block_height=max_block_height,
        min_size=QUESTION_MIN_FONT_SIZE, max_size=max_size,
        size_step=QUESTION_FONT_SIZE_STEP, max_lines=QUESTION_MAX_LINES,
        line_spacing=QUESTION_LINE_SPACING,
    )

    # Center the WHOLE group (question block + gap + divider) as one
    # unit within the stage region, rather than bottom-anchoring to a
    # fixed divider position. Narration's hero region is close in
    # scale to its text, so bottom-anchoring there only ever leaves a
    # small gap; this frame's stage is much larger than any realistic
    # question, so bottom-anchoring left a large, unintended empty gap
    # above the text instead. Centering the group fixes that while
    # keeping the same "cohesive group, not independent elements"
    # philosophy.
    block_height = line_height * len(lines)
    group_height = block_height + QUESTION_GROUP_GAP + DIVIDER_THICKNESS
    group_top = QUESTION_STAGE_TOP + max(0, (stage_height - group_height) / 2)

    block_top = group_top
    block_bottom = block_top + block_height
    divider_y = block_bottom + QUESTION_GROUP_GAP

    first_line_y = block_top + (line_height / 2)

    text_color = getattr(ctx, "question_text_color", None) or QUESTION_GOLD

    for i, line in enumerate(lines):
        y = first_line_y + (i * line_height)
        draw.text((542, y + 2), line, font=font_question, fill=(0, 0, 0, 200), anchor="mm")
        draw.text((540, y), line, font=font_question, fill=text_color, anchor="mm")

    # Same divider element narration_scene.py uses above its scene
    # dots -- identical color/thickness/span, deliberately reused as a
    # visual callback rather than a new closing motif.
    draw_archival_divider(draw, center_x=540, y=divider_y, total_width=480)

    draw.text((542, profile.watermark_y + 2), ctx.watermark_text, font=font_brand, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((540, profile.watermark_y), ctx.watermark_text, font=font_brand, fill=(255, 255, 255, 160), anchor="mm")

    frame_path = f"{ctx.work_dir}/frame_{segment.id}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path