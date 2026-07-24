"""
core/renderers/narration_scene.py

Direct port of the original post.py `build_frame()`. Behavior is
preserved exactly; the only changes are:
  - "SweetyStoryLab" watermark string -> ctx.watermark_text
  - hardcoded font path -> ctx.font_path
  - scene dot count -> derived from ctx.total_narration_scenes instead
    of a hardcoded "2 minus index" assuming exactly 3 scenes

That last point is flagged in the Assumption Audit: the original dot
indicator ("● ● ○") silently assumed a 3-scene story. Generalizing it
is REQUIRED for arbitrary segment counts to render correctly, so it's
made explicit here rather than left as a hidden 3-scene assumption.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def render(segment, ctx) -> str:
    img = Image.open(ctx.image_path).convert("RGB")

    bg = img.resize((1080, 1920), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
    darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
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
    canvas.paste(img_main, (0, 420))

    canvas_rgba = canvas.convert("RGBA")
    top_bar = Image.new("RGBA", (1080, 380), (0, 0, 0, 200))
    canvas_rgba.paste(top_bar, (0, 0), top_bar)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    try:
        font_title = ImageFont.truetype(ctx.font_path, 48)
        font_brand = ImageFont.truetype(ctx.font_path, 26)
        font_scene = ImageFont.truetype(ctx.font_path, 22)
    except Exception:
        font_title = font_brand = font_scene = ImageFont.load_default()

    display_title = ctx.title if len(ctx.title) <= 28 else ctx.title[:25] + "..."
    draw.text((542, 152), display_title, font=font_title, fill=(0, 0, 0, 200), anchor="mm")
    draw.text((540, 150), display_title, font=font_title, fill=(255, 255, 255, 255), anchor="mm")

    draw.rectangle([300, 200, 780, 203], fill=(255, 255, 255, 140))

    # Generalized scene indicator: filled dots = segments up to and
    # including this one, hollow dots = remaining narration segments.
    # (Original hardcoded "2 - index" assuming exactly 3 scenes.)
    total = ctx.total_narration_scenes
    filled = ctx.scene_index + 1
    dots = "\u25cf " * filled + "\u25cb " * max(0, total - filled)
    draw.text((540, 230), dots.strip(), font=font_scene, fill=(255, 255, 255, 180), anchor="mm")

    draw.text((542, 1882), ctx.watermark_text, font=font_brand, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((540, 1880), ctx.watermark_text, font=font_brand, fill=(255, 255, 255, 160), anchor="mm")

    frame_path = f"{ctx.work_dir}/frame_{segment.id}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path
