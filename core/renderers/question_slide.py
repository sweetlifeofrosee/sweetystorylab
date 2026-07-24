"""
core/renderers/question_slide.py

Direct port of the original post.py `build_question_frame()`.
Genre-neutral: works for a horror comment-bait question exactly as
well as a mystery-archive closing question, since the text itself is
brand/prompt content, not renderer logic.
"""
import textwrap
from PIL import Image, ImageDraw, ImageFont


def render(segment, ctx) -> str:
    try:
        img = Image.open(ctx.image_path).convert("RGB")
        bg = img.resize((1080, 1920), Image.LANCZOS)
        bg = bg.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(radius=30))
        darkener = Image.new("RGB", (1080, 1920), (0, 0, 0))
        canvas = Image.blend(bg, darkener, 0.80)
    except Exception:
        canvas = Image.new("RGB", (1080, 1920), (0, 0, 0))

    draw = ImageDraw.Draw(canvas)
    try:
        font_question = ImageFont.truetype(ctx.font_path, 52)
        font_brand = ImageFont.truetype(ctx.font_path, 26)
    except Exception:
        font_question = font_brand = ImageFont.load_default()

    wrapped = textwrap.wrap(segment.text, width=22)
    line_height = 72
    total_height = len(wrapped) * line_height
    start_y = 960 - total_height // 2

    for i, line in enumerate(wrapped):
        y = start_y + (i * line_height)
        for offset in [(3, 3), (2, 2), (1, 1)]:
            draw.text((540 + offset[0], y + offset[1]), line, font=font_question,
                       fill=(0, 0, 0, 180), anchor="mm")
        draw.text((540, y), line, font=font_question, fill=(255, 255, 255, 255), anchor="mm")

    draw.text((542, 1882), ctx.watermark_text, font=font_brand, fill=(150, 150, 150, 180), anchor="mm")
    draw.text((540, 1880), ctx.watermark_text, font=font_brand, fill=(255, 255, 255, 160), anchor="mm")

    frame_path = f"{ctx.work_dir}/frame_{segment.id}.jpg"
    canvas.save(frame_path, "JPEG", quality=95)
    return frame_path
