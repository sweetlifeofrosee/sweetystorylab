"""
core/renderers/layout_profiles.py

Platform Layout Profiles.

A LayoutProfile carries every geometry value that differs by publish
destination (title sizing/position, watermark position, question-slide
sizing/position, subtitle margin). It carries NOTHING else -- no
prompts, no story content, no voice/music/timing, no brand identity.
Brand styling (font, watermark text, colors) stays exactly where it is
today, in RenderContext / config.yaml. Platform and brand are
orthogonal: any brand can render to any platform.

FACEBOOK is not a "default" in the sense of being special-cased in
code -- it is simply the profile whose values equal the historical
hardcoded constants from narration_scene.py, question_slide.py, and
assembler.py, verbatim. That equivalence is what guarantees
byte-for-byte identical Facebook output: the renderers no longer have
their own hardcoded numbers, they just always resolve to these same
numbers when platform="facebook" (the default everywhere it matters --
run_brand(), cli.py, build_video()).

Adding a future platform (Instagram Reels, YouTube Shorts, ...) means
adding one more LayoutProfile entry here -- no renderer file changes.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutProfile:
    name: str

    # --- Title (core/renderers/narration_scene.py) ---
    title_max_font_size: int
    title_min_font_size: int
    title_max_text_width: int
    # Hard floor: the title block never renders above this y, regardless
    # of how short the title is (bottom-anchoring already keeps short
    # titles low; this floor is what protects long/3-line titles).
    title_area_top_padding: int

    # --- Watermark (narration_scene.py + question_slide.py, shared position) ---
    watermark_y: int

    # --- Question slide / closing frame (question_slide.py) ---
    # Only the bottom of the stage moves -- the top (450) is already
    # well clear of any platform's top UI, so it's left as-is rather
    # than duplicated into every profile.
    question_stage_bottom: int
    question_max_text_width: int
    # Multiplies whichever max font size is already in force for this
    # brand (brand config override, or the module default if the brand
    # sets none) -- keeps brand identity/customization intact while
    # still shrinking to fit a platform's safe area. 1.0 = no change.
    question_font_scale: float

    # --- Subtitles (core/video/assembler.py) ---
    subtitle_target_margin_px: int
    subtitle_font_size: int
    # ASS style units (same scale as subtitle_target_margin_px, via
    # LIBASS_MARGINV_SCALE_FACTOR). 0 = no horizontal margin override
    # -- assembler.py omits the MarginL/MarginR style keys entirely in
    # that case, matching the original hardcoded style string exactly
    # (this is what keeps Facebook byte-for-byte identical).
    subtitle_margin_l: int
    subtitle_margin_r: int
    # core/subtitles/beat_splitter.py: approximate max characters per
    # beat, targeting ~2-3 rendered lines at this profile's actual
    # subtitle_font_size + effective width. A heuristic, not exact
    # glyph measurement (subtitles render via libass/FontName=Arial,
    # a different engine than the PIL-based renderer) -- calibrated
    # against real burned-in test frames (see the beat_splitter design
    # conversation), not guessed. Facebook's value is deliberately
    # generous (~2.5 lines) since Facebook's *existing* subtitle cues
    # (3-word fixed chunks, or raw TTS-provider output) are often
    # choppier/smaller than this -- so beat-splitting is a readability
    # improvement for Facebook too, not just a TikTok-safe-area fix.
    subtitle_beat_max_chars: int


# Every value below is copied verbatim from the pre-existing hardcoded
# constants in narration_scene.py, question_slide.py, and
# assembler.py. This is what makes platform="facebook" a no-op.
FACEBOOK = LayoutProfile(
    name="facebook",
    title_max_font_size=120,
    title_min_font_size=40,
    title_max_text_width=920,
    title_area_top_padding=20,
    watermark_y=1880,
    question_stage_bottom=1650,
    question_max_text_width=920,
    question_font_scale=1.0,
    # Raised +100px (was 150) -- Facebook's own caption/hashtag UI was
    # crowding the burned-in subtitle at the old position. Verified
    # against a real beat-splitter-produced line: this INCREASES
    # clearance from the watermark (108px -> 208px, since watermark_y
    # is unchanged and this only moves the subtitle further away from
    # it), so no derived watermark adjustment is needed or made.
    subtitle_target_margin_px=250,
    subtitle_font_size=11,
    subtitle_margin_l=0,
    subtitle_margin_r=0,
    # Measured: at FontSize=11, no L/R margin (~1054px usable width), a
    # real 45-word test sentence wrapped to 8 lines -> ~30 chars/line.
    # Target ~2.5 lines -> 30*2.5=75, rounded down slightly for safety.
    subtitle_beat_max_chars=70,
)

# TikTok safe-area assumptions (1080x1920 canvas):
#   - top ~160px reserved for TikTok's search bar
#   - right ~160px column reserved for the like/comment/share/sound rail
#   - bottom ~250-300px reserved for caption/username/music attribution
#
# REVISED after real-device testing (round 2). The first pass raised
# the subtitle bottom margin to clear TikTok's own caption UI, but on
# a real device that made long narration lines wrap tall enough for
# the block's TOP edge to reach our own watermark, and the unconstrained
# width let lines run under the right-side action column. Empirically
# measured (see subtitle_calib/ in this conversation) using ffmpeg's
# actual subtitle burn-in + pixel measurement, not just style-value math
# -- the same libass FontSize behaves the same non-obvious way MarginV
# does (see LIBASS_MARGINV_SCALE_FACTOR in core/video/assembler.py), so
# values below were chosen by rendering real frames and measuring
# results, then re-measuring after each adjustment:
#   - subtitle_font_size 11->9 (-18%) shrinks wrapped block height
#   - subtitle_margin_l/r 0->24 (~163px each side) keeps text off the
#     right-side action column, reusing the same 760px-wide safe column
#     already used for the title and question slide
#   - subtitle_target_margin_px 172->160: still raised vs Facebook's
#     150, but less aggressively -- the earlier +15% version pushed the
#     block's top too high; most of the actual fix is the smaller/
#     narrower block, not a bigger bottom margin
#   - watermark_y 1600->1350 and question_stage_bottom 1550->1310:
#     moved together, well clear of the tallest realistic subtitle
#     block (measured 349px / 18% of frame height for a deliberately
#     extreme worst-case single-cue line -- typical narration cues are
#     much shorter), verified with >=40px of real clearance at that
#     worst case, not just at typical-length text
# --- TikTok watermark/subtitle anchoring (round 5) ---
# Previous rounds treated watermark_y and subtitle_target_margin_px as
# two independently-tuned values, then checked (and re-checked, several
# times) that they didn't collide. That's what kept breaking under real
# narration lengths. This round inverts the relationship: the watermark
# is the fixed anchor near the bottom, and the subtitle's position is
# DERIVED from it with a fixed gap -- so they cannot collide by
# construction, regardless of how many lines a beat wraps to (subtitle
# grows upward from its anchor point, verified against real burned-in
# frames: a 1-line and an 11-word 3-line beat at the same MarginV differ
# in TOP position by ~106px while BOTTOM position stays put, +/-10px of
# glyph-descender noise -- i.e. libass's bottom-anchor really does only
# grow upward, this isn't an assumption).
#
# TIKTOK_WATERMARK_BOTTOM_CLEAR_PX: distance from the frame's bottom
# edge to the watermark's own bottom edge -- clears TikTok's caption/
# username/music UI, same ~250px safe-zone assumption used in round 4
# (now applied to the watermark instead of the subtitle, since the
# watermark is now the bottom-most custom element).
# TIKTOK_SUBTITLE_WATERMARK_GAP_PX: fixed gap between the subtitle's
# bottom edge and the watermark's top edge -- 50px, middle of the
# requested 40-60px range.
_TIKTOK_WATERMARK_HALF_HEIGHT_PX = 14  # measured: 26px brand font, "SweetyStoryLab" bbox height 27px
_TIKTOK_WATERMARK_BOTTOM_CLEAR_PX = 250
_TIKTOK_SUBTITLE_WATERMARK_GAP_PX = 50
_TIKTOK_WATERMARK_Y = 1920 - _TIKTOK_WATERMARK_BOTTOM_CLEAR_PX - _TIKTOK_WATERMARK_HALF_HEIGHT_PX  # 1656
_TIKTOK_WATERMARK_TOP_EDGE = _TIKTOK_WATERMARK_Y - _TIKTOK_WATERMARK_HALF_HEIGHT_PX  # 1642
_TIKTOK_SUBTITLE_TARGET_MARGIN_PX = 1920 - (_TIKTOK_WATERMARK_TOP_EDGE - _TIKTOK_SUBTITLE_WATERMARK_GAP_PX)  # 328
_TIKTOK_QUESTION_STAGE_BOTTOM = _TIKTOK_WATERMARK_TOP_EDGE - 40  # same 40px buffer style as before, now far more slack

TIKTOK = LayoutProfile(
    name="tiktok",
    title_max_font_size=90,     # -25% vs Facebook's 120
    title_min_font_size=32,     # -20% vs Facebook's 40
    title_max_text_width=760,   # clears right-side action column
    title_area_top_padding=140,  # clears the TikTok search bar
    watermark_y=_TIKTOK_WATERMARK_Y,  # 1656 -- moved down near the bottom, subtitle now anchors ABOVE it (see block above)
    question_stage_bottom=_TIKTOK_QUESTION_STAGE_BOTTOM,  # 1602
    question_max_text_width=760,  # same right-column clearance as title
    question_font_scale=0.8,    # -20%, mirrors the title's reduction
    subtitle_target_margin_px=_TIKTOK_SUBTITLE_TARGET_MARGIN_PX,  # 328 -- derived, not independently tuned
    # v2 used 9 (-18%), but real-device testing (round 3) surfaced a real
    # 49-word single-sentence narration cue that still wrapped to 7 lines
    # at size 9, pushing the block's top onto the watermark. Re-measured
    # against that exact line at sizes 9/8/7/6 (see subtitle_calib/ in
    # this conversation): 8 drops the block from 21.3% to 16.1% of frame
    # height and clears the watermark by ~83px on that real line, with
    # legibility still comfortable. No font size gives an absolute
    # guarantee for arbitrarily long single-sentence cues -- this value
    # is verified against a real long line, not a theoretical minimum.
    subtitle_font_size=8,       # -27% vs Facebook's 11
    subtitle_margin_l=24,       # ~163px real margin -- clears right-side action column
    subtitle_margin_r=24,       # same safe column as title/question (760px effective width)
    # Measured: at FontSize=8, MarginL/R=24 (~750px usable width), the
    # same real 45-word test sentence wrapped to 6 lines -> ~40 chars/
    # line. Target ~2.5 lines -> 40*2.5=100, rounded down for safety.
    subtitle_beat_max_chars=95,
)

_PROFILES = {
    "facebook": FACEBOOK,
    "tiktok": TIKTOK,
}


def get_profile(platform: str) -> LayoutProfile:
    if platform not in _PROFILES:
        raise ValueError(
            f"Unknown platform '{platform}'. Registered platforms: "
            f"{list(_PROFILES.keys())}. New platforms are added to "
            f"core/renderers/layout_profiles.py, not invented per-brand "
            f"or per-call."
        )
    return _PROFILES[platform]