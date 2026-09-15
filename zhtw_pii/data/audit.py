"""Draw the manual label audit of test set v0, and check the filled-in result.

`sample` writes `data/testset/v0/AUDIT.md` as a blank template: a fixed-seed
sample of 30 rows from the committed `test.jsonl`, each labeled span shown
with its boundaries bracketed inside the original text, and no question
answered. `check` enforces the freeze rule in `docs/OPERATIONS.md`: test set
v0 is frozen only once AUDIT.md records a PASS with every question answered.
No audit yet, or one still being filled in with nothing changed beyond its
answers, is a legal not-yet-frozen state and passes. A PASS with any gap
fails, and so does a `data/CHANGELOG.md` (which exists only after v0 has
been frozen) without a PASS.

The sample depends on the committed file and a pinned seed alone. The
generator is never re-run, so the audited rows are exactly the rows the
benchmark scores.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import random
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from zhtw_pii.data.generate import Entity, Example

# The name written into AUDIT.md stays fixed; the path read from can differ
# (tests, another working directory) without changing the rendered template.
TESTSET_NAME = "data/testset/v0/test.jsonl"
TESTSET_PATH = Path(TESTSET_NAME)
AUDIT_PATH = Path("data/testset/v0/AUDIT.md")
CHANGELOG_PATH = Path("data/CHANGELOG.md")

# AUDIT.md records exactly the draw and the template text this module renders.
# Once it holds answers, changing the seed, the cells, or any rendered line makes
# `check` fail on it, and regenerating erases the answers: version a new audit
# (for example for test set v1) instead of editing these for v0.
# Python guarantees only random() and seeding to stay the same across versions;
# the draw also relies on choice() and shuffle(), so it is reproducible because
# pyproject.toml pins requires-python to 3.11.
AUDIT_SEED = 42
AUDIT_SAMPLE_SIZE = 30

SPAN_OPEN = "⟦"
SPAN_CLOSE = "⟧"
SPAN_OPTIONS = ("agree", "disagree")
UNLABELED_OPTIONS = ("no", "yes")
PASS_OPTION = "PASS: no systematic labeling error; freeze the test set as it is"
FAIL_OPTION = "FAIL: systematic labeling error found; fix and regenerate before freezing"
UNLABELED_HEADING = "### Unlabeled entities"
VERDICT_HEADING = "## Verdict"
METHOD_HEADING = "## How the sample was drawn"
VERDICT = "verdict"
DATE_FIELD = "Date (YYYY-MM-DD)"

# Kept here rather than imported from generate.HONORIFICS, so that a later
# generator change cannot silently change which v0 rows the audit samples.
_HONORIFIC_SUFFIXES = ("先生", "小姐", "女士")
_MARKUP_CHARACTERS = frozenset({SPAN_OPEN, SPAN_CLOSE, "`", "\n", "\r"})
_SECTION_LOCATIONS = {"## How to answer": "instructions", METHOD_HEADING: "sample method"}
_MAX_DIFFERENCES_SHOWN = 8

_HEADING = re.compile(r"#{1,6} ")
_ROW_HEADING = re.compile(r"## Row (\d+) of \d+: (\S+)")
_SPAN_HEADING = re.compile(r"### Span (\d+) of \d+: ")
_BOX = re.compile(r"[-*+][ \t]+\[([^\]]*)\](.*)")
_FIELD = re.compile(r"(Note|Reviewer|" + re.escape(DATE_FIELD) + r"|Summary):(.*)")
_TABLE_SEPARATOR_CELL = re.compile(r":?-+:?")
_RECORDED_SHA256 = re.compile(r"^- Test set SHA-256: `([0-9a-f]{64})`$", re.MULTILINE)


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_testset(path: Path) -> list[Example]:
    """Read the committed test set in file order.

    Raises:
        ValueError: if a row's spans are empty, leave its text, or overlap,
            or its text contains a character the template uses as markup;
            such a row could not be shown to the reviewer faithfully.
    """
    examples: list[Example] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        example = Example(
            id=row["id"],
            text=row["text"],
            entities=[Entity(e["start"], e["end"], e["label"]) for e in row["entities"]],
            tier=row["tier"],
            seed=row["seed"],
            template_id=row["template_id"],
        )
        problem = _display_problem(example)
        if problem is not None:
            raise ValueError(f"{path}:{line_number} ({example.id}): {problem}")
        examples.append(example)
    return examples


def _display_problem(example: Example) -> str | None:
    """Say why a row cannot be rendered faithfully, or None if it can."""
    markup = sorted(_MARKUP_CHARACTERS & set(example.text))
    if markup:
        return f"text contains {markup}, which the audit template uses as markup"
    cursor = 0
    for entity in sorted(example.entities, key=lambda entity: (entity.start, entity.end)):
        if not cursor <= entity.start < entity.end <= len(example.text):
            return f"span {entity} is empty, out of range, or overlaps the span before it"
        cursor = entity.end
    return None


def coverage_cells(example: Example) -> frozenset[str]:
    """Return the sampling cells a row belongs to.

    A cell is one generator mechanism a systematic labeling error could be
    tied to: the row's tier, its template, the surface form of each labeled
    span, and, for rows with spans, whether punctuation was removed. Every
    template ends with `。` and punctuation removal deletes it, so a missing
    `。` identifies that transform from the text alone.
    """
    cells = {f"tier: {example.tier}", f"template: {example.template_id}"}
    for entity in example.entities:
        cells.add(_span_form(entity.label, example.text[entity.start : entity.end]))
    if example.entities and "。" not in example.text:
        cells.add("text: punctuation removed")
    return frozenset(cells)


def _span_form(label: str, surface: str) -> str:
    """Name the surface form of one labeled span, as a coverage cell."""
    if label == "PERSON":
        honorific = next((h for h in _HONORIFIC_SUFFIXES if surface.endswith(h)), None)
        if honorific is None:
            return f"PERSON: {len(surface)}-character name"
        # Every v0 surname is a single character.
        if len(surface) == len(honorific) + 1:
            return "PERSON: surname + honorific"
        return "PERSON: full name + honorific"
    if label == "ADDRESS":
        if not surface.endswith("號"):
            return "ADDRESS: city and district only"
        if any("０" <= char <= "９" for char in surface):
            return "ADDRESS: street, fullwidth digits"
        return "ADDRESS: street, ASCII digits"
    return label


def select_audit_sample(
    examples: Sequence[Example], size: int = AUDIT_SAMPLE_SIZE, seed: int = AUDIT_SEED
) -> list[Example]:
    """Draw the audit rows: cover every cell once, fill the rest uniformly, then shuffle.

    Cells are visited from fewest rows to most; each cell that no chosen row
    covers yet gets one row drawn uniformly from its unchosen rows. The
    remaining slots are drawn uniformly from all unchosen rows. A single
    `random.Random(seed)` makes every draw, so the result depends only on
    `examples` (in order), `size`, and `seed`.

    Raises:
        ValueError: if `size` exceeds the number of rows, or covering every
            cell takes more than `size` rows.
    """
    if size > len(examples):
        raise ValueError(f"cannot sample {size} rows from a test set of {len(examples)}")
    rng = random.Random(seed)
    cells = [coverage_cells(example) for example in examples]
    population = Counter(cell for row_cells in cells for cell in row_cells)
    chosen: list[int] = []
    covered: set[str] = set()
    for cell in sorted(population, key=lambda name: (population[name], name)):
        if cell in covered:
            continue
        candidates = [i for i, row in enumerate(cells) if cell in row and i not in chosen]
        chosen.append(rng.choice(candidates))
        covered |= cells[chosen[-1]]
    if len(chosen) > size:
        raise ValueError(
            f"covering all {len(population)} cells took {len(chosen)} rows, "
            f"more than the {size} requested"
        )
    rest = [i for i in range(len(examples)) if i not in chosen]
    rng.shuffle(rest)
    chosen.extend(rest[: size - len(chosen)])
    rng.shuffle(chosen)
    return [examples[i] for i in chosen]


def mark_spans(text: str, entities: Sequence[Entity]) -> str:
    """Wrap each entity's characters in ⟦ ⟧ inside `text`, leaving every other character."""
    pieces: list[str] = []
    cursor = 0
    for entity in sorted(entities, key=lambda entity: (entity.start, entity.end)):
        inside = text[entity.start : entity.end]
        pieces.append(f"{text[cursor : entity.start]}{SPAN_OPEN}{inside}{SPAN_CLOSE}")
        cursor = entity.end
    pieces.append(text[cursor:])
    return "".join(pieces)


def render_blank_audit(
    examples: Sequence[Example],
    testset_sha256: str,
    size: int = AUDIT_SAMPLE_SIZE,
    seed: int = AUDIT_SEED,
) -> str:
    """Render the audit template for `examples` with every question unanswered."""
    sample = select_audit_sample(examples, size=size, seed=seed)
    lines = _render_header(len(examples), testset_sha256, size, seed)
    for position, example in enumerate(sample, start=1):
        lines += _render_row(position, size, example)
    lines += _render_verdict()
    lines += _render_method(examples, sample, seed)
    return "\n".join(lines) + "\n"


def _render_header(n_rows: int, testset_sha256: str, size: int, seed: int) -> list[str]:
    return [
        "# Test set v0 label audit",
        "",
        f"A manual check of the gold labels in `{TESTSET_NAME}` (issue #4) on {size} of",
        f"its {n_rows} rows. `make audit-sample` generated this file with every question",
        "blank; every answer in it is written by hand.",
        "",
        f"- Test set SHA-256: `{testset_sha256}`",
        f"- Sample: {size} rows, seed {seed}, drawn as described at the end of this file",
        "",
        "## How to answer",
        "",
        "Each row shows its text, one question per labeled span, and a last question about",
        "anything left unlabeled. Labeled characters are wrapped in ⟦ ⟧ inside the original",
        "text, so a boundary that is one character off shows as a bracket in the wrong place.",
        "",
        "- **Span**: `agree` if you would annotate exactly the characters inside ⟦ ⟧, no more",
        "  and no fewer, with that label. Otherwise `disagree`, and write in the note what",
        "  the span or label should be.",
        "- **Unlabeled entities**: `yes` if the text holds a PERSON, ADDRESS, or ORG that is",
        "  not inside ⟦ ⟧, and write it and its label in the note. Otherwise `no`.",
        "- Labels: PERSON is a person's name, ADDRESS is an address, ORG is an",
        "  organization's name. Format-defined identifiers such as ID or phone numbers are",
        "  out of scope (`docs/adr/0002-exclude-format-defined-entities.md`).",
        "- Judge each row the way you would annotate its text yourself, not by how the",
        "  generator is known to build rows.",
        "- Mark exactly one box per question: replace the space inside `[ ]` with `x`, so",
        "  it reads `[x]`. A note is required after `disagree` or `yes` and optional",
        "  otherwise; write it after `Note:`, never on the box line. It may run several",
        "  lines. Leave every other line as it is.",
        "- Run `make audit-check` before each commit. It names the line of anything it",
        "  cannot read.",
        "",
        "Record the verdict at the end once every question is answered. A PASS is what",
        "freezes the test set (`docs/OPERATIONS.md`). `make audit-check`, which CI runs,",
        "fails a PASS that leaves a question unanswered or a `disagree` or `yes` without a",
        "note, and fails if any line other than a box mark or field text is edited.",
        "",
    ]


def _render_row(position: int, total: int, example: Example) -> list[str]:
    span_count = len(example.entities)
    lines = [
        "---",
        "",
        f"## Row {position} of {total}: {example.id}",
        "",
        f"Tier `{example.tier}`, template `{example.template_id}`, labeled spans: {span_count}.",
        "",
        f"Text: `{example.text}`",
        "",
    ]
    for index, entity in enumerate(example.entities, start=1):
        lines += [
            f"### Span {index} of {span_count}: {entity.label}, "
            f"start={entity.start}, end={entity.end}",
            "",
            f"`{mark_spans(example.text, [entity])}`",
            "",
            *[f"- [ ] {option}" for option in SPAN_OPTIONS],
            "",
            "Note:",
            "",
        ]
    return lines + [
        UNLABELED_HEADING,
        "",
        f"`{mark_spans(example.text, example.entities)}`",
        "",
        "Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?",
        "",
        *[f"- [ ] {option}" for option in UNLABELED_OPTIONS],
        "",
        "Note:",
        "",
    ]


def _render_verdict() -> list[str]:
    return [
        "---",
        "",
        VERDICT_HEADING,
        "",
        "Record this once every question above is answered. In the summary, describe any",
        "pattern across the `disagree` and `yes` answers, or say there were none.",
        "",
        f"- [ ] {PASS_OPTION}",
        f"- [ ] {FAIL_OPTION}",
        "",
        "Reviewer:",
        "",
        f"{DATE_FIELD}:",
        "",
        "Summary:",
        "",
    ]


def _render_method(examples: Sequence[Example], sample: Sequence[Example], seed: int) -> list[str]:
    population = Counter(cell for example in examples for cell in coverage_cells(example))
    in_sample = Counter(cell for example in sample for cell in coverage_cells(example))
    rows = len(sample)
    bound = f"{1 - 0.05 ** (1 / rows):.1%}"
    lines = [
        "---",
        "",
        METHOD_HEADING,
        "",
        "This audit looks for systematic labeling errors. An error tied to one template, one",
        "surface form of an entity, or one noise transform repeats on every row that shares",
        "it, so the draw makes sure each of those appears at least once. It is not an error",
        f"rate estimate. Zero errors in {rows} rows would still allow a rate as high as {bound}",
        "(one-sided 95 percent upper bound), and the draw is not uniform, so do not quote an",
        "error rate from this file.",
        "",
        "Each row belongs to a few cells: its tier, its template, the form of each labeled",
        "span, and, for rows with spans, whether punctuation was removed (the text has no",
        f"`。`, which every template ends with). Using `random.Random({seed})`, cells are",
        "visited from fewest rows to most, and each cell that no chosen row covers yet gets",
        "one row drawn uniformly from its unchosen rows. The remaining slots are drawn",
        "uniformly from all unchosen rows, and the chosen rows are shuffled into the order",
        "above. `make audit-check` repeats the draw and fails if the rows above differ.",
        "",
        "| Cell | Rows in test set | Rows in this sample |",
        "|---|---|---|",
    ]
    return lines + [f"| {c} | {population[c]} | {in_sample[c]} |" for c in sorted(population)]


@dataclass
class Question:
    """One question as written in an audit file: where it is, its options, marks, and fields."""

    location: str
    options: tuple[str, ...]
    marked: list[str] = field(default_factory=list)
    fields: dict[str, list[str]] = field(default_factory=dict)

    def text_of(self, name: str) -> str:
        """Return the stripped text written after one of this question's fields."""
        return "\n".join(self.fields.get(name, [])).strip()


@dataclass(frozen=True)
class _TemplateLine:
    """A line reduced to what the template fixes, with its file line number and question."""

    text: str
    number: int
    location: str


@dataclass
class _Scan:
    """Everything one pass over an audit file finds."""

    lines: list[_TemplateLine] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    unreadable_boxes: list[str] = field(default_factory=list)


def _lines(text: str) -> list[str]:
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    return [line.rstrip() for line in text.split("\n")]


def _scan(text: str) -> _Scan:
    """Read an audit file once: its template lines, its answers, and any box it cannot read.

    Field text (after Note:, Reviewer:, and the rest) runs until the next
    heading, rule, box, or field. Box marks, field text, blank lines,
    trailing spaces, and a table's column padding are left out of the
    template lines, so they are the only differences the template comparison
    tolerates.
    """
    scan = _Scan()
    row, location = "", "header"
    open_field: list[str] | None = None
    for number, line in enumerate(_lines(text), start=1):
        box = _BOX.fullmatch(line)
        answer_field = _FIELD.fullmatch(line)
        ends_field = bool(box or answer_field or _HEADING.match(line) or line == "---")
        if open_field is not None and not ends_field:
            open_field.append(line)
            continue
        open_field = None
        row, location, question = _enter_section(line, row, location)
        if question is not None:
            scan.questions.append(question)
        if box:
            _read_box(scan, box, number, location)
        elif answer_field:
            name, open_field = answer_field.group(1), [answer_field.group(2)]
            scan.lines.append(_TemplateLine(f"{name}:", number, location))
            if scan.questions:
                scan.questions[-1].fields[name] = open_field
        elif line:
            scan.lines.append(_TemplateLine(_normalize_table_row(line), number, location))
    return scan


def _enter_section(line: str, row: str, location: str) -> tuple[str, str, Question | None]:
    """Track the row and question a line belongs to, starting a Question at its heading."""
    if match := _ROW_HEADING.fullmatch(line):
        row = f"row {match.group(1)} ({match.group(2)})"
        return row, row, None
    if match := _SPAN_HEADING.match(line):
        location = f"{row}, span {match.group(1)}"
        return row, location, Question(location, SPAN_OPTIONS)
    if line == UNLABELED_HEADING:
        location = f"{row}, unlabeled entities"
        return row, location, Question(location, UNLABELED_OPTIONS)
    if line == VERDICT_HEADING:
        return row, VERDICT, Question(VERDICT, (PASS_OPTION, FAIL_OPTION))
    return row, _SECTION_LOCATIONS.get(line, location), None


def _read_box(scan: _Scan, box: re.Match[str], number: int, location: str) -> None:
    """Record a box line: its label as template text, and an x inside it as an answer."""
    label = box.group(2).strip()
    scan.lines.append(_TemplateLine(f"- [ ] {label}", number, location))
    mark = box.group(1).strip()
    if not mark:
        return
    # A CJK input method left in fullwidth mode types \uff58 or \uff38 for x. List them
    # explicitly: NFKC would also accept look-alikes such as the Roman numeral ten.
    if mark not in ("x", "X", "\uff58", "\uff38"):
        scan.unreadable_boxes.append(
            f"line {number}, {location}: the box before {label!r} holds {box.group(1)!r}; "
            "replace the space inside [ ] with a plain x to mark it, or leave it empty"
        )
    elif scan.questions:
        scan.questions[-1].marked.append(label)


def _normalize_table_row(line: str) -> str:
    """Compare table rows by cell content, so a formatter's column padding is not an edit."""
    if not line.startswith("|"):
        return line
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if all(_TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in cells):
        cells = ["---"] * len(cells)
    return "| " + " | ".join(cells) + " |"


def parse_answers(text: str) -> list[Question]:
    """Read every question's options, marked boxes, and field text from an audit file."""
    return _scan(text).questions


@dataclass(frozen=True)
class AuditCheck:
    """What `check_audit` found: the audit's state, and every reason the state is invalid."""

    state: str
    problems: tuple[str, ...]
    total: int
    incomplete: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when the committed audit state is legal."""
        return not self.problems

    @property
    def complete(self) -> int:
        """Row questions with exactly one box marked and any required note written."""
        return self.total - len(self.incomplete)


def check_audit(audit_path: Path, testset_path: Path, changelog_path: Path) -> AuditCheck:
    """Check the committed audit state against the freeze rule in docs/OPERATIONS.md."""
    frozen_by_changelog = changelog_path.exists()
    if not audit_path.exists():
        if frozen_by_changelog:
            problem = _changelog_problem(changelog_path, f"{audit_path} does not exist")
            return AuditCheck("not started", (problem,), 0, ())
        return AuditCheck("not started", (), 0, ())
    text = audit_path.read_text(encoding="utf-8")
    scan = _scan(text)
    row_questions = [question for question in scan.questions if question.location != VERDICT]
    incomplete = [gap for question in row_questions if (gap := _incompleteness(question))]
    verdict, verdict_problems = _read_verdict(scan.questions)
    problems = scan.unreadable_boxes + _integrity_problems(text, scan, testset_path)
    problems += verdict_problems
    if verdict == "PASS":
        problems += incomplete
    if frozen_by_changelog and verdict != "PASS":
        problems.append(_changelog_problem(changelog_path, f"{audit_path} records no PASS"))
    state = verdict or "in progress"
    return AuditCheck(state, tuple(problems), len(row_questions), tuple(incomplete))


def _incompleteness(question: Question) -> str | None:
    """Say what a row question still needs, or None once it is fully answered."""
    for label in question.marked:
        if label not in question.options:
            return (
                f"{question.location}: a marked box reads {label!r}, not "
                f"{' or '.join(question.options)}; a note goes after Note:, not on the box line"
            )
    if not question.marked:
        return f"{question.location}: no box marked"
    if len(question.marked) > 1:
        return f"{question.location}: {len(question.marked)} boxes marked; mark exactly one"
    if question.marked[0] in ("disagree", "yes") and not question.text_of("Note"):
        return f"{question.location}: '{question.marked[0]}' needs a note saying what is wrong"
    return None


def _read_verdict(questions: Sequence[Question]) -> tuple[str | None, list[str]]:
    """Return the marked verdict (PASS, FAIL, or None) and what its block is missing."""
    verdict = next((question for question in questions if question.location == VERDICT), None)
    if verdict is None or not verdict.marked:
        return None, []
    if len(verdict.marked) > 1:
        return None, ["verdict: PASS and FAIL are both marked; mark exactly one"]
    if verdict.marked[0] not in verdict.options:
        return None, [f"verdict: the marked box reads {verdict.marked[0]!r}, not PASS or FAIL"]
    decision = verdict.marked[0].split(":")[0]
    problems = [
        f"verdict: {decision} needs the {name}: field filled in"
        for name in ("Reviewer", "Summary")
        if not verdict.text_of(name)
    ]
    written_date = verdict.text_of(DATE_FIELD)
    if not _is_calendar_date(written_date):
        problems.append(f"verdict: {DATE_FIELD} must be a real date, got {written_date!r}")
    return decision, problems


def _is_calendar_date(text: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _changelog_problem(changelog_path: Path, audit_state: str) -> str:
    return (
        f"{changelog_path} exists, which marks test set v0 as frozen (data/DATA_CARD.md), "
        f"but {audit_state}. Record a PASS in the audit before adding the changelog."
    )


def _integrity_problems(audit_text: str, scan: _Scan, testset_path: Path) -> list[str]:
    """Explain, line by line, where an audit file departs from its template."""
    testset_sha256 = sha256_file(testset_path)
    recorded = _RECORDED_SHA256.search("\n".join(_lines(audit_text)))
    if recorded is not None and recorded.group(1) != testset_sha256:
        return [
            f"the audit was generated for a test set with SHA-256 {recorded.group(1)}, but "
            f"{testset_path} is now {testset_sha256}, so its rows are not the benchmarked "
            "rows. Start a fresh audit with `make audit-sample FORCE=1`; the earlier answers "
            "stay in git history."
        ]
    blank = render_blank_audit(load_testset(testset_path), testset_sha256)
    differences = _differences(_scan(blank).lines, scan.lines)
    if not differences:
        return []
    shown = [f"  {difference}" for difference in differences[:_MAX_DIFFERENCES_SHOWN]]
    if len(differences) > _MAX_DIFFERENCES_SHOWN:
        shown.append(f"  and {len(differences) - _MAX_DIFFERENCES_SHOWN} more")
    return [
        "the audit does not match its template in more than answers; only the mark inside "
        f"a box and the text after Note:, Reviewer:, {DATE_FIELD}:, and Summary: may differ.\n"
        + "\n".join(shown)
        + "\n  If AUDIT.md was not edited at these lines, the template changed instead: "
        "the rendered text, cells, or seed in zhtw_pii/data/audit.py."
    ]


def _differences(expected: Sequence[_TemplateLine], actual: Sequence[_TemplateLine]) -> list[str]:
    """Describe each place the file's lines depart from the template's, by file line."""
    matcher = difflib.SequenceMatcher(
        a=[line.text for line in expected], b=[line.text for line in actual], autojunk=False
    )
    found: list[str] = []
    for tag, want_start, want_end, got_start, got_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        for offset in range(max(want_end - want_start, got_end - got_start)):
            has_want = want_start + offset < want_end
            has_got = got_start + offset < got_end
            if has_want and has_got:
                found.append(_replaced(expected[want_start + offset], actual[got_start + offset]))
            elif has_want:
                want = expected[want_start + offset]
                where = (
                    f"near line {actual[got_end].number}"
                    if got_end < len(actual)
                    else "at the end of the file"
                )
                found.append(f"{where}, {want.location}: missing {want.text!r}")
            else:
                got = actual[got_start + offset]
                found.append(
                    f"line {got.number}, {got.location}: unexpected {got.text!r}; "
                    "if this is a note, write it after Note:"
                )
    return found


def _replaced(want: _TemplateLine, got: _TemplateLine) -> str:
    hint = ""
    if want.text.startswith("- [ ] ") and got.text.startswith(f"{want.text} "):
        hint = "; a note goes after Note:, not on the box line"
    return f"line {got.number}, {got.location}: expected {want.text!r}, found {got.text!r}{hint}"


def write_blank_audit(testset_path: Path, audit_path: Path, force: bool = False) -> None:
    """Write the blank audit template for the committed test set.

    Raises:
        FileExistsError: if `audit_path` exists and `force` is False, since
            the file may already hold review answers that would be erased.
    """
    if audit_path.exists() and not force:
        raise FileExistsError(
            f"{audit_path} already exists and may hold review answers, which regenerating "
            "would erase. Run `make audit-sample FORCE=1` to overwrite it anyway."
        )
    blank = render_blank_audit(load_testset(testset_path), sha256_file(testset_path))
    audit_path.write_text(blank, encoding="utf-8")


def _print_check(check: AuditCheck) -> None:
    if not check.ok:
        print(f"audit-check failed for {AUDIT_PATH}:", file=sys.stderr)
        for problem in check.problems:
            print(f"- {problem}", file=sys.stderr)
    elif check.state == "not started":
        print(f"{AUDIT_PATH} does not exist yet, so test set v0 is not frozen.")
    elif check.state == "in progress":
        print(
            f"{AUDIT_PATH} has no verdict yet, so test set v0 is not frozen; "
            f"{check.complete} of {check.total} questions complete."
        )
        for gap in check.incomplete[:5]:
            print(f"  next: {gap}")
    elif check.state == "FAIL":
        print(f"{AUDIT_PATH} records a FAIL, so test set v0 is not frozen.")
    else:
        print(
            f"{AUDIT_PATH} records a PASS with all {check.total} questions answered, "
            "so test set v0 is frozen."
        )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for `python -m zhtw_pii.data.audit`."""
    parser = argparse.ArgumentParser(description="Manual label audit of test set v0.")
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("sample", help=f"write the blank template to {AUDIT_PATH}")
    sample.add_argument(
        "--force", action="store_true", help="overwrite an existing AUDIT.md and its answers"
    )
    commands.add_parser("check", help="exit 1 if the audit state breaks the freeze rule")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for `python -m zhtw_pii.data.audit`."""
    args = build_arg_parser().parse_args(argv)
    if args.command == "sample":
        try:
            write_blank_audit(TESTSET_PATH, AUDIT_PATH, force=args.force)
        except FileExistsError as error:
            print(error, file=sys.stderr)
            sys.exit(1)
        print(f"wrote {AUDIT_PATH}: {AUDIT_SAMPLE_SIZE} rows, seed {AUDIT_SEED}")
        return
    check = check_audit(AUDIT_PATH, TESTSET_PATH, CHANGELOG_PATH)
    _print_check(check)
    sys.exit(0 if check.ok else 1)


if __name__ == "__main__":
    main()
