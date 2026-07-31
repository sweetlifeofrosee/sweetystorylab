"""
core/renderers/text_layout.py

Shared adaptive text wrapping/sizing logic, extracted from
narration_scene.py so question_slide.py can reuse it without
duplicating the algorithm. This is internal rendering-subsystem
machinery, not a public interface, not brand-facing, and not a schema
concern -- it exists purely because two renderer files need the exact
same generic capability (wrap into N balanced lines, pick the largest
font size that fits a given box), each with their own size/width/height
bounds.

This is NOT the same situation as the Horror Lab / Mystery Lab parser
duplication decision -- that was two BRANDS independently owning
similar-looking but brand-specific logic, kept deliberately separate.
This is one CORE subsystem needing identical generic logic twice;
sharing it here avoids maintaining two copies of the same algorithm
for no benefit.
"""
from PIL import ImageFont


def text_width(draw, text, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def wrap_balanced(draw, text, font, max_width, max_lines=3):
    """Wrap `text` into at most `max_lines` lines, each fitting within
    `max_width` at the given font, choosing the split point(s) that
    minimize the difference between line widths (a "balanced" wrap,
    not a naive first-fit). Falls back to a best-effort greedy wrap if
    no split satisfies max_width within max_lines."""
    words = text.split()
    if not words:
        return [text]

    if text_width(draw, text, font) <= max_width:
        return [text]

    def line_width(ws):
        return text_width(draw, " ".join(ws), font)

    def try_split(num_lines):
        n = len(words)
        if num_lines == 1:
            return [words] if line_width(words) <= max_width else None

        best = None
        best_spread = None

        def recurse(start, remaining_lines, current_split):
            nonlocal best, best_spread
            if remaining_lines == 1:
                candidate = current_split + [words[start:n]]
                widths = [line_width(part) for part in candidate]
                if all(w <= max_width for w in widths) and all(len(part) > 0 for part in candidate):
                    spread = max(widths) - min(widths)
                    if best_spread is None or spread < best_spread:
                        best = candidate
                        best_spread = spread
                return
            for split_at in range(start + 1, n):
                recurse(split_at, remaining_lines - 1, current_split + [words[start:split_at]])

        recurse(0, num_lines, [])
        return best

    for num_lines in range(2, max_lines + 1):
        result = try_split(num_lines)
        if result is not None:
            return [" ".join(part) for part in result]

    # Best-effort fallback: naive greedy wrap into max_lines, even if a
    # line ends up exceeding max_width (e.g. one very long word).
    lines, current = [], []
    for word in words:
        candidate = current + [word]
        if line_width(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(" ".join(current))
            current = [word]
        if len(lines) == max_lines - 1:
            break
    if current:
        lines.append(" ".join(current))
    return lines[:max_lines] if lines else [text]


def draw_archival_divider(draw, center_x, y, total_width,
                           line_color=(255, 255, 255, 140),
                           diamond_color=(255, 255, 255, 180),
                           diamond_size=14, line_thickness=2, gap=10):
    """Shared divider motif: a thin horizontal rule broken by a small
    centered diamond outline. Used identically by narration_scene.py
    (above the scene dots) and question_slide.py (below the closing
    question) -- a deliberate shared visual element, not decoration
    reinvented per frame type."""
    half_width = total_width // 2
    left_x = center_x - half_width
    right_x = center_x + half_width
    diamond_half = diamond_size // 2

    left_line_end = center_x - diamond_half - gap
    right_line_start = center_x + diamond_half + gap
    draw.line([(left_x, y), (left_line_end, y)], fill=line_color, width=line_thickness)
    draw.line([(right_line_start, y), (right_x, y)], fill=line_color, width=line_thickness)

    points = [
        (center_x, y - diamond_half),
        (center_x + diamond_half, y),
        (center_x, y + diamond_half),
        (center_x - diamond_half, y),
        (center_x, y - diamond_half),
    ]
    draw.line(points, fill=diamond_color, width=line_thickness, joint="curve")


def fit_text(draw, text, font_path, max_width, max_block_height,
             min_size, max_size, size_step=4, max_lines=3, line_spacing=1.15):
    """Search from max_size down to min_size and return
    (lines, font, line_height) for the largest size whose wrapped
    (<=max_lines) block fits inside max_block_height. Falls back to
    min_size, best-effort, if nothing fits cleanly."""
    size = max_size
    last_attempt = None
    while size >= min_size:
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            font = ImageFont.load_default()
        lines = wrap_balanced(draw, text, font, max_width, max_lines)
        line_height = int(size * line_spacing)
        block_height = line_height * len(lines)
        all_fit_width = all(text_width(draw, line, font) <= max_width for line in lines)
        last_attempt = (lines, font, line_height)
        if len(lines) <= max_lines and block_height <= max_block_height and all_fit_width:
            return lines, font, line_height
        size -= size_step

    return last_attempt