"""
core/subtitles/beat_splitter.py

Phase 1 of the subtitle presentation redesign (see conversation/design
doc -- full architecture proposal covered a shared TTS-provider-level
WordTiming abstraction; this is the deliberately smaller first step).

WHAT THIS DOES: takes the .srt file that core/providers/tts/
orchestrator.py already produces today -- via EITHER TTS path
(ElevenLabs primary, fixed 3-word chunks; or Edge TTS fallback,
whatever cue granularity edge-tts's own SubMaker emitted) -- and
regroups it into readable "reading beats" of ~2-3 rendered lines,
breaking at natural phrase boundaries (sentence/clause punctuation)
instead of a fixed word count or whatever the TTS engine happened to
emit. Genre-neutral, platform-driven only via the two char-count
arguments (see subtitle_beat_max_chars in core/renderers/
layout_profiles.py) -- no story, brand, or platform logic lives here.

WHAT THIS DELIBERATELY DOES NOT DO (Phase 1 scope, by design):
  - Does NOT touch either TTS provider or orchestrator.py's existing
    generate_voice/generate_srt_from_voice/vtt_to_srt functions. This
    is a pure post-processing pass on the .srt file those already
    produce, regardless of which path produced it.
  - Does NOT introduce a shared WordTiming abstraction across TTS
    providers -- that's the larger Phase 2 refactor, only worth doing
    if this smaller version proves out.
  - Does NOT touch audio in any way.
  - Does NOT measure real glyph widths via libass (the engine that
    actually burns subtitles) or via PIL (the engine the renderer uses
    for titles, which uses a different font entirely -- subtitles are
    always FontName=Arial per assembler.py, regardless of brand font).
    Real per-glyph measurement would mean rendering candidate beats
    through ffmpeg to check, which is expensive to do word-by-word.
    Instead this uses a chars-per-line heuristic, calibrated against
    real rendered output (see subtitle_beat_max_chars comments in
    layout_profiles.py) rather than guessed. This is standard practice
    for caption line-breaking and is a deliberate, documented Phase 1
    simplification -- worth knowing if beat lengths ever look
    noticeably off in practice.

TIMING: a cue's existing [start, end] span is treated as authoritative
and is distributed evenly across its own words -- the exact same
linear-interpolation technique orchestrator.py's
generate_srt_from_voice() already uses (duration / word_count), just
reapplied locally to each existing cue's own (already-precise) span
instead of to the whole narration segment at once. This adds no new
timing assumption beyond what the pipeline already relies on
elsewhere, and a beat's span is always exactly the union of its member
words' spans -- so whatever's on screen at any instant is, by
construction, whatever was estimated to be spoken at that instant.
Sync accuracy is therefore never worse than what the input .srt
already had; it can only be as good as the input's own granularity
(a single very coarse input cue can't be un-coarsened without real
word-level timing from the TTS engine itself -- see the Phase 2
proposal for that).
"""
from dataclasses import dataclass
from typing import List


@dataclass
class Cue:
    start: float  # seconds
    end: float    # seconds
    text: str


@dataclass
class WordSpan:
    word: str
    start: float
    end: float


# Punctuation that ends a natural phrase/clause -- strongly prefer
# cutting a beat right after one of these.
_HARD_BREAK_SUFFIXES = (".", "!", "?", ",", ";", ":", "\u2014")

# Conjunctions that often start a new clause -- mildly prefer cutting
# a beat right before one of these, if no hard break is closer.
_SOFT_BREAK_WORDS = {
    "and", "but", "or", "so", "yet", "when", "because", "while", "as",
    "that", "which", "since", "then",
}


def _parse_srt_timestamp(ts: str) -> float:
    h, m, rest = ts.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _format_srt_timestamp(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60); t -= m * 60
    s = int(t)
    ms = int(round((t - s) * 1000))
    if ms == 1000:  # rounding edge case
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(srt_path: str) -> List[Cue]:
    with open(srt_path, "r", encoding="utf-8") as f:
        raw = f.read()

    cues = []
    for block in raw.strip().split("\n\n"):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        timing_line = next((l for l in lines if "-->" in l), None)
        if not timing_line:
            continue
        start_str, end_str = [p.strip() for p in timing_line.split("-->")]
        text_lines = [
            l for l in lines
            if "-->" not in l and not l.strip().isdigit()
        ]
        text = " ".join(text_lines).strip()
        if text:
            cues.append(Cue(
                start=_parse_srt_timestamp(start_str),
                end=_parse_srt_timestamp(end_str),
                text=text,
            ))
    return cues


def expand_cue_to_words(cue: Cue) -> List[WordSpan]:
    words = cue.text.split()
    if not words:
        return []
    duration = max(cue.end - cue.start, 0.0)
    per_word = duration / len(words)
    return [
        WordSpan(word=w, start=cue.start + i * per_word, end=cue.start + (i + 1) * per_word)
        for i, w in enumerate(words)
    ]


def _ends_with_hard_break(word: str) -> bool:
    return bool(word) and word[-1:] in _HARD_BREAK_SUFFIXES


def _is_soft_break_word(word: str) -> bool:
    return word.strip(".,!?;:\u2014\"'").lower() in _SOFT_BREAK_WORDS


def split_into_beats(words: List[WordSpan], max_chars: int, min_chars: int = 10,
                      lookahead_words: int = 4) -> List[Cue]:
    """Greedy, single-pass, deterministic. Never reorders, drops, or
    rewrites a word -- the only decision made is where, between two
    already-fixed and already-timed words, to insert a cue boundary."""
    beats: List[Cue] = []
    n = len(words)
    i = 0

    while i < n:
        j = i
        cur_len = 0
        cut_at = None

        while j < n:
            w = words[j]
            add_len = len(w.word) + (1 if j > i else 0)  # +1 for the joining space
            if cur_len + add_len > max_chars and j > i:
                break
            cur_len += add_len
            j += 1

            if cur_len >= min_chars:
                if _ends_with_hard_break(w.word):
                    cut_at = j
                    break
                # Look a little further ahead for a nearby hard break --
                # this is what produces natural, uneven beat lengths
                # instead of always cutting at the first minimum-length
                # opportunity.
                probe_len = cur_len
                found = False
                for k in range(j, min(j + lookahead_words, n)):
                    probe_len += len(words[k].word) + 1
                    if probe_len > max_chars:
                        break
                    if _ends_with_hard_break(words[k].word):
                        j = k + 1
                        cur_len = probe_len
                        found = True
                        break
                    if k + 1 < n and _is_soft_break_word(words[k + 1].word):
                        j = k + 1
                        cur_len = probe_len
                        found = True
                        break
                if found:
                    cut_at = j
                    break

        if cut_at is None:
            cut_at = max(j, i + 1)  # always make forward progress

        beat_words = words[i:cut_at]
        if beat_words:
            beats.append(Cue(
                start=beat_words[0].start,
                end=beat_words[-1].end,
                text=" ".join(w.word for w in beat_words),
            ))
        i = cut_at

    return beats


def write_srt(cues: List[Cue], out_path: str) -> None:
    blocks = [
        f"{idx}\n{_format_srt_timestamp(c.start)} --> {_format_srt_timestamp(c.end)}\n{c.text}"
        for idx, c in enumerate(cues, start=1)
    ]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks))


def rewrite_srt_as_beats(input_srt_path: str, output_srt_path: str,
                          max_chars: int, min_chars: int = 10) -> str:
    """Phase 1 entry point -- called once from run.py, after whichever
    TTS path already produced input_srt_path, before build_video()
    burns the result in. See module docstring for exactly what this
    does and does not change."""
    cues = parse_srt(input_srt_path)
    words: List[WordSpan] = []
    for cue in cues:
        words.extend(expand_cue_to_words(cue))
    beats = split_into_beats(words, max_chars=max_chars, min_chars=min_chars)
    write_srt(beats, output_srt_path)
    return output_srt_path
