"""
core/renderers/narration_scene.py

Direct port of the original post.py `build_frame()`, extended with an
adaptive hero title treatment. The wrap/fit algorithm itself now lives
in core/renderers/text_layout.py, shared with question_slide.py --
this file owns only its own layout constants and drawing calls.

Layout notes:
  - Hero region: HERO_HEIGHT=480px (~25% of frame).
  - Title wraps into up to 3 balanced lines, adaptively sized between
    a platform-supplied min/max font size (see core/renderers/
    layout_profiles.py -- title_min_font_size / title_max_font_size).
  - Title block is bottom-anchored to the divider (TITLE_GROUP_GAP
    above it), not centered independently -- title, divider, and
    scene dots read as one composed group; leftover space is absorbed
    above the title, not wedged between title and divider. The
    platform's title_area_top_padding acts as a hard floor on top of
    this, so long titles can never render above a platform's unsafe
    top zone (e.g. TikTok's search bar).
  - Main photo paste offset: y=500 (below the enlarged hero region).
    This, HERO_HEIGHT, and the divider/scene-dot position are the same
    for every platform -- only text sizing/position and the watermark
    move; image placement is deliberately untouched (see brief).

Platform selection: `ctx.layout_profile` (set by core/pipeline/run.py
from core/renderers/layout_profiles.py) supplies every value that
varies by platform. Facebook's profile values equal the historical
hardcoded constants this file used to define directly -- so
platform="facebook" (the default) produces byte-identical output to
before this change.

Unchanged: subtitle rendering (owned by core/video/assembler.py),
scene-dot indicator logic (position stays attached to the divider,
which does not move by platform).
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .text_layout import fit_text, draw_archival_divider
from .layout_profiles import FACEBOOK as _DEFAULT_PROFILE

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

HERO_HEIGHT = 480
HERO_FOOTER_HEIGHT = 100
TITLE_AREA_HEIGHT = HERO_HEIGHT - HERO_FOOTER_HEIGHT
TITLE_AREA_BOTTOM_PADDING = 20

TITLE_FONT_SIZE_STEP = 4
TITLE_MAX_LINES = 3
TITLE_LINE_SPACING = 1.15
TITLE_GROUP_GAP = 30   # gap between the bottom of the title block and the divider below it

IMAGE_PASTE_Y = HERO_HEIGHT + 20


def render(segment, ctx) -> str:
    # Defensive fallback (e.g. a RenderContext built without going
    # through run_brand()) -- resolves to the exact same constants this
    # file used to hardcode, so behavior is unchanged either way.
    profile = getattr(ctx, "layout_profile", None) or _DEFAULT_PROFILE

    img = Image.open(ctx.image_path).convert("RGB")

    bg = img.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
    darkener = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0))
    bg = Image.blend(bg, darkener, 0.6)

    img_main = img.resize((1080, 1080), Image.LANCZOS)

    grad = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(grad)
    for i in range(500):
        alpha = int((i / 500) * 220)
        grad_draw.rectangle([0, 580 + i, 1080, 581 + i], fill=(0, 0, 0, alpha))
    img_rgba = img_main.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, grad)
    img_main = img_rgba.convert("RGB")

    canvas = bg.copy()
    canvas.paste(img_main, (0, IMAGE_PASTE_Y))

    canvas_rgba = canvas.convert("RGBA")
    top_bar = Image.new("RGBA", (CANVAS_WIDTH, HERO_HEIGHT), (0, 0, 0, 200))
    canvas_rgba.paste(top_bar, (0, 0), top_bar)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    try:
        font_brand = ImageFont.truetype(ctx.font_path, 26)
        font_scene = ImageFont.truetype(ctx.font_path, 22)
    except Exception:
        font_brand = font_scene = ImageFont.load_default()

    max_block_height = TITLE_AREA_HEIGHT - profile.title_area_top_padding - TITLE_AREA_BOTTOM_PADDING
    lines, font_title, line_height = fit_text(
        draw, ctx.title, ctx.font_path,
        max_width=profile.title_max_text_width, max_block_height=max_block_height,
        min_size=profile.title_min_font_size, max_size=profile.title_max_font_size,
        size_step=TITLE_FONT_SIZE_STEP, max_lines=TITLE_MAX_LINES,
        line_spacing=TITLE_LINE_SPACING,
    )

    divider_y = TITLE_AREA_HEIGHT + 20
    dots_y = TITLE_AREA_HEIGHT + 55

    block_height = line_height * len(lines)
    block_bottom = divider_y - TITLE_GROUP_GAP
    block_top = max(block_bottom - block_height, profile.title_area_top_padding)
    first_line_y = block_top + (line_height / 2)

    for i, line in enumerate(lines):
        y = first_line_y + (i * line_height)
        draw.text((542, y + 2), line, font=font_title, fill=(0, 0, 0, 200), anchor="mm")
        draw.text((540, y), line, font=font_title, fill=(255, 255, 255, 255), anchor="mm")

    draw_archival_divider(draw, center_x=540, y=divider_y, total_width=480)

    total = ctx.total_narration_scenes
    filled = ctx.scene_index + 1
    dots = "\u25cf " * filled + "\u25cb " * max(0, total - filled)
    draw.text((540, dots_y), dots.strip(), font=font_scene, fill=(255, 255, 255, 180), anchor="mm")

    draw.text((542, profile.watermark_y + 2), ctx.watermark_text, font=font_brand, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((540, profile.watermark_y), ctx.watermark_text, font=font_brand, fill=(255, 255, 255, 160), anchor="mm")

    frame_path = f"{ctx.work_dir}/frame_{segment.id}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path