"""
brands/mystery_lab/dedup.py

Lightweight, brand-owned subject deduplication. Core (engine.py) only
knows "call is_acceptable(story), and if rejected, call retry_hint(story)
for feedback to include in the next attempt" -- it has no idea this
means "check a JSON file," that's entirely this file's concern.

No curated topic database: this only ever knows about subjects the
model itself has actually generated and had accepted, recorded as
they occur. It does not pre-populate or seed the list with anything.

Persistence: a single flat JSON file, brands/mystery_lab/used_subjects.json,
containing {"used_subjects": ["Nazca Lines", "Antikythera Mechanism", ...]}.
Comparison is case-insensitive and strips a leading "the " so "The
Indus Valley Civilization" and "Indus Valley Civilization" are treated
as the same subject.
"""
import json
import os


class MysteryLabSubjectDeduplicator:
    def __init__(self, brand_id: str = "mystery_lab",
                 storage_path: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "used_subjects.json"
        )
        self._used = self._load()

    def _load(self):
        if not os.path.exists(self.storage_path):
            return set()
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(self._normalize(s) for s in data.get("used_subjects", []))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable file -- fail open (treat as empty)
            # rather than crash the whole pipeline over a bookkeeping file.
            return set()

    def _save(self, raw_subjects):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump({"used_subjects": sorted(raw_subjects)}, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _normalize(subject: str) -> str:
        s = subject.strip().lower()
        if s.startswith("the "):
            s = s[4:]
        return s

    def is_acceptable(self, story) -> bool:
        subject = getattr(story, "primary_subject", None)
        if not subject:
            # No subject captured (e.g. malformed LLM output that still
            # passed generic validation) -- fail open, don't block
            # generation on missing dedup data.
            return True

        normalized = self._normalize(subject)
        if normalized in self._used:
            return False

        # Record immediately on acceptance -- exactly one record per
        # story actually returned by generate_story().
        self._used.add(normalized)
        self._persist_raw_subject(subject)
        return True

    def _persist_raw_subject(self, subject: str):
        # Re-read current raw list (not just normalized set) so we
        # preserve original casing/spelling in the stored file, then
        # append and save.
        raw = []
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    raw = json.load(f).get("used_subjects", [])
            except (json.JSONDecodeError, OSError):
                raw = []
        raw.append(subject.strip())
        self._save(raw)

    def retry_hint(self, story) -> str:
        subject = getattr(story, "primary_subject", "that subject")
        return (
            f"You previously chose \"{subject}\" in this attempt, but it has "
            f"already been covered in a previous Mystery Lab episode. Choose "
            f"a completely different primary subject, civilization, culture, "
            f"artifact, site, or figure -- ideally from a different category, "
            f"era, and region than before."
        )