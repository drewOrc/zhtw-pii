"""Zero-dependency regex baseline: a naive lower bound for entity detection.

No ML and no external packages; everything here is the standard library.
This baseline exists to be weak in a specific, documented way, so its
numbers establish the floor that Presidio, GLiNER, an LLM, and any future
trained model are expected to clear. See `docs/adr/0002` for why
PERSON/ADDRESS/ORG were chosen precisely because a format-free regex
cannot solve them well.

Design deviations from a literal "surname + 1-2 characters + optional
honorific" pattern, and why:

- The PERSON pattern accepts a **zero-character given name when an
  honorific follows** ("張先生", "蕭女士"): checking the generator
  (`zhtw_pii.data.generate.generate_person`) shows that 70% of its
  honorific-bearing names use only the surname's first character plus the
  honorific, with no given-name characters at all. A regex that required
  1-2 given-name characters unconditionally would miss most honorific
  names in the test set, and bare "surname + honorific" is also just how
  Chinese address-by-title works in general, not an artifact of this
  synthetic generator. The alternative (0 given-name characters, no
  honorific) is deliberately excluded: without a following honorific, a
  bare surname character is common enough as an ordinary word (a name
  component, part of a place name) that allowing it would collapse
  precision.
- The given-name character class has no dictionary or stoplist; it is
  `[一-鿿]{1,2}` (written as a literal character range,
  `一` to `鿿`, in the compiled pattern below), any 1-2 CJK Unified
  Ideographs. This is intentional, not an oversight: a real "naive regex"
  has no notion of which characters are name-like, and the resulting
  boundary bleed into adjacent real words (a given name match absorbing
  the next word's first character) is exactly the kind of failure this
  baseline is supposed to demonstrate.
- The ORG prefix before a legal suffix ("...有限公司" etc.) is bounded to
  non-punctuation characters, not the literal `\\S{1,8}` a first reading
  of the spec suggests. Plain `\\S` also matches full-width and half-width
  punctuation, so an unbounded version matches straight through a
  sentence's clause-separating colon or comma and absorbs the preceding
  clause into the "company name" (observed on the test set: "本月請款
  單位：集賢有限公司" matched as one span starting at "單位："). That is a
  bug a punctuation boundary trivially avoids, not a meaningful part of
  what this baseline is meant to demonstrate, so it is excluded.
"""

from __future__ import annotations

import re
from pathlib import Path

from zhtw_pii.eval.types import BaselineMetadata, Span

_LEXICON_DIR = Path(__file__).parent / "lexicon"


def _read_lines(path: Path) -> tuple[str, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(line.strip() for line in lines if line.strip() and not line.startswith("#"))


TOP100_SURNAMES: tuple[str, ...] = _read_lines(_LEXICON_DIR / "top100_surnames.txt")
COUNTIES_AND_CITIES: tuple[str, ...] = _read_lines(_LEXICON_DIR / "counties_and_cities.txt")
HONORIFICS: tuple[str, ...] = ("先生", "小姐", "女士")
ORG_SUFFIXES: tuple[str, ...] = (
    "股份有限公司",
    "有限公司",
    "診所",
    "事務所",
    "工作室",
    "基金會",
    "協會",
    "銀行",
    "醫院",
)
_DISTRICT_SUFFIXES = "區鄉鎮市"
_NON_PUNCTUATION = r"[^\s，。：；、！？,.:;!?]"


def _alternation(words: tuple[str, ...]) -> str:
    """Build a regex alternation, longest word first so prefixes never shadow it."""
    return "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))


_HONORIFIC_GROUP = f"(?:{_alternation(HONORIFICS)})"
_PERSON_PATTERN = re.compile(
    rf"(?:{_alternation(TOP100_SURNAMES)})"
    rf"(?:[一-鿿]{{1,2}}{_HONORIFIC_GROUP}?|{_HONORIFIC_GROUP})"
)

_ADDRESS_PATTERN = re.compile(
    rf"(?:{_alternation(COUNTIES_AND_CITIES)})"
    rf"{_NON_PUNCTUATION}{{1,3}}[{_DISTRICT_SUFFIXES}]"
    rf"(?:{_NON_PUNCTUATION}{{1,10}}(?:路|街|大道){_NON_PUNCTUATION}{{0,15}}號)?"
)

_ORG_PATTERN = re.compile(rf"{_NON_PUNCTUATION}{{2,8}}(?:{_alternation(ORG_SUFFIXES)})")

_LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PERSON", _PERSON_PATTERN),
    ("ADDRESS", _ADDRESS_PATTERN),
    ("ORG", _ORG_PATTERN),
)


def predict_spans(text: str) -> list[Span]:
    """Run all three label patterns over `text` and return sorted spans."""
    spans = [
        Span(start=match.start(), end=match.end(), label=label)
        for label, pattern in _LABEL_PATTERNS
        for match in pattern.finditer(text)
    ]
    spans.sort(key=lambda span: (span.start, span.end, span.label))
    return spans


class RegexBaseline:
    """Sanity-lower-bound baseline built from surname, city, and org-suffix lists."""

    name = "regex"
    label_mapping = {"PERSON": "PERSON", "ADDRESS": "ADDRESS", "ORG": "ORG"}
    params: dict[str, object] = {
        "surname_count": len(TOP100_SURNAMES),
        "county_city_count": len(COUNTIES_AND_CITIES),
        "org_suffix_count": len(ORG_SUFFIXES),
        "given_name_chars": "1-2 unconstrained CJK ideographs, or 0 with a mandatory honorific",
    }

    def load(self) -> BaselineMetadata:
        """Regex has nothing to download or import; this only reports metadata."""
        return BaselineMetadata(
            model_id="zhtw-pii-regex-rules",
            model_version="1.0.0",
            size_mb=None,
            data_leaves_machine=False,
            bytes_sent=None,
            package_versions={},
        )

    def predict(self, text: str) -> list[Span]:
        """Return regex-matched PERSON/ADDRESS/ORG spans for one input string."""
        return predict_spans(text)
