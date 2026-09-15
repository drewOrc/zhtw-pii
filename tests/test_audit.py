"""Unit tests for zhtw_pii.data.audit.

Every test writes its own test set into tmp_path with the generator, so
nothing here reads or writes the committed data/testset/v0/ files.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from zhtw_pii.data import audit, generate
from zhtw_pii.data.generate import Entity, Example

pytestmark = pytest.mark.unit

REVIEW_DATE = "2026-09-16"


@pytest.fixture
def testset_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.jsonl"
    generate.write_jsonl(generate.generate_dataset(seed=42), path)
    return path


def _blank(testset_path: Path, seed: int = audit.AUDIT_SEED) -> str:
    examples = audit.load_testset(testset_path)
    return audit.render_blank_audit(examples, audit.sha256_file(testset_path), seed=seed)


def _answered_pass(blank: str, box: str = "- [x]") -> str:
    """Answer every span agree and every row no, then record a signed PASS."""
    return (
        blank.replace("- [ ] agree", f"{box} agree")
        .replace("- [ ] no", f"{box} no")
        .replace("- [ ] PASS:", f"{box} PASS:")
        .replace("Reviewer:", "Reviewer: Test Reviewer")
        .replace(f"{audit.DATE_FIELD}:", f"{audit.DATE_FIELD}: {REVIEW_DATE}")
        .replace("Summary:", "Summary: No disagreements.")
    )


def _check(
    tmp_path: Path, testset_path: Path, audit_text: str | None, changelog: bool = False
) -> audit.AuditCheck:
    audit_path = tmp_path / "AUDIT.md"
    if audit_text is not None:
        audit_path.write_text(audit_text, encoding="utf-8")
    changelog_path = tmp_path / "CHANGELOG.md"
    if changelog:
        changelog_path.write_text("# Changelog\n", encoding="utf-8")
    return audit.check_audit(audit_path, testset_path, changelog_path)


def _line_number_of(text: str, line: str) -> int:
    return text.split("\n").index(line) + 1


def _first_span_location(text: str) -> str:
    return next(q.location for q in audit.parse_answers(text) if q.options == audit.SPAN_OPTIONS)


def _row(text: str, surface: str, label: str) -> Example:
    start = text.index(surface)
    entity = Entity(start, start + len(surface), label)
    return Example(id="row", text=text, entities=[entity], tier="hard", seed=42, template_id="t")


def test_rendered_template_is_identical_across_runs(testset_path):
    assert _blank(testset_path) == _blank(testset_path)


def test_sample_is_thirty_distinct_rows_of_the_test_set(testset_path):
    examples = audit.load_testset(testset_path)
    sample_ids = [example.id for example in audit.select_audit_sample(examples)]
    assert len(sample_ids) == audit.AUDIT_SAMPLE_SIZE == 30
    assert len(set(sample_ids)) == 30
    assert set(sample_ids) <= {example.id for example in examples}


@pytest.mark.parametrize(("dataset_seed", "sample_seed"), [(42, 42), (43, 7), (44, 2026)])
def test_sample_covers_every_cell_that_occurs_in_the_test_set(dataset_seed, sample_seed):
    examples = generate.generate_dataset(seed=dataset_seed)
    sample = audit.select_audit_sample(examples, seed=sample_seed)
    population = {cell for example in examples for cell in audit.coverage_cells(example)}
    covered = {cell for example in sample for cell in audit.coverage_cells(example)}
    assert covered == population
    assert {"PERSON: surname + honorific", "PERSON: full name + honorific"} <= covered
    assert {"tier: negative", "ADDRESS: city and district only"} <= covered


@pytest.mark.parametrize(
    ("text", "surface", "label", "form"),
    [
        ("姓名：吳詠。", "吳詠", "PERSON", "PERSON: 2-character name"),
        ("姓名：吳詠恩。", "吳詠恩", "PERSON", "PERSON: 3-character name"),
        ("您好我是吳先生。", "吳先生", "PERSON", "PERSON: surname + honorific"),
        ("您好我是吳詠小姐。", "吳詠小姐", "PERSON", "PERSON: full name + honorific"),
        (
            "地址：台北市中正區中山路1段2號。",
            "台北市中正區中山路1段2號",
            "ADDRESS",
            "ADDRESS: street, ASCII digits",
        ),
        (
            "地址：台北市中正區中山路１段２號。",
            "台北市中正區中山路１段２號",
            "ADDRESS",
            "ADDRESS: street, fullwidth digits",
        ),
        ("地址：台北市中正區。", "台北市中正區", "ADDRESS", "ADDRESS: city and district only"),
        ("本月請款單位：誠信診所。", "誠信診所", "ORG", "ORG"),
    ],
)
def test_coverage_cells_name_the_surface_form_of_a_span(text, surface, label, form):
    assert form in audit.coverage_cells(_row(text, surface, label))


def test_punctuation_removal_is_a_cell_only_for_rows_with_spans():
    removed = "text: punctuation removed"
    assert removed in audit.coverage_cells(_row("姓名吳詠", "吳詠", "PERSON"))
    assert removed not in audit.coverage_cells(_row("姓名：吳詠。", "吳詠", "PERSON"))
    negative = Example(
        id="n",
        text="訂單編號A123已出貨",
        entities=[],
        tier="negative",
        seed=42,
        template_id="neg_01",
    )
    assert removed not in audit.coverage_cells(negative)


def test_sample_refuses_a_size_too_small_to_cover_every_cell(testset_path):
    with pytest.raises(ValueError, match="covering all"):
        audit.select_audit_sample(audit.load_testset(testset_path), size=3)


def test_sample_refuses_a_size_larger_than_the_test_set(testset_path):
    with pytest.raises(ValueError, match="cannot sample"):
        audit.select_audit_sample(audit.load_testset(testset_path)[:10], size=11)


def test_marked_text_shows_a_span_that_is_one_character_too_long():
    text = "姓名：吳詠。"
    assert audit.mark_spans(text, [Entity(3, 5, "PERSON")]) == "姓名：⟦吳詠⟧。"
    assert audit.mark_spans(text, [Entity(3, 6, "PERSON")]) == "姓名：⟦吳詠。⟧"


def test_marked_text_brackets_every_span_of_a_row_in_place():
    text = "應徵者吳詠投遞了誠信診所的職缺。"
    entities = [Entity(8, 12, "ORG"), Entity(3, 5, "PERSON")]
    assert audit.mark_spans(text, entities) == "應徵者⟦吳詠⟧投遞了⟦誠信診所⟧的職缺。"


def test_blank_template_answers_nothing_and_asks_about_every_span_and_every_row(testset_path):
    sample = audit.select_audit_sample(audit.load_testset(testset_path))
    questions = audit.parse_answers(_blank(testset_path))
    assert len(questions) == sum(len(example.entities) for example in sample) + len(sample) + 1
    assert not any(question.marked for question in questions)
    assert not any(question.text_of(name) for question in questions for name in question.fields)


def test_load_testset_rejects_a_row_whose_text_contains_a_bracket_character(tmp_path):
    path = tmp_path / "test.jsonl"
    row = _row("姓名：⟦吳詠。", "吳詠", "PERSON")
    generate.write_jsonl([row], path)
    with pytest.raises(ValueError, match="markup"):
        audit.load_testset(path)


def test_writing_the_template_never_overwrites_an_existing_audit_without_force(
    tmp_path, testset_path
):
    audit_path = tmp_path / "AUDIT.md"
    audit_path.write_text("answers in progress\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        audit.write_blank_audit(testset_path, audit_path)
    assert audit_path.read_text(encoding="utf-8") == "answers in progress\n"
    audit.write_blank_audit(testset_path, audit_path, force=True)
    assert audit_path.read_text(encoding="utf-8") == _blank(testset_path)


def test_check_passes_when_no_audit_has_been_started(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, None)
    assert result.ok, result.problems
    assert result.state == "not started"


def test_check_passes_for_the_blank_template_as_generated(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, _blank(testset_path))
    assert result.ok, result.problems
    assert (result.state, result.complete) == ("in progress", 0)
    assert result.total > audit.AUDIT_SAMPLE_SIZE


def test_check_passes_for_a_partly_answered_audit_with_no_verdict(tmp_path, testset_path):
    partial = _blank(testset_path).replace("- [ ] agree", "- [x] agree", 5)
    result = _check(tmp_path, testset_path, partial)
    assert result.ok, result.problems
    assert (result.state, result.complete) == ("in progress", 5)


def test_check_passes_for_a_pass_with_every_question_answered(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, _answered_pass(_blank(testset_path)))
    assert result.ok, result.problems
    assert result.state == "PASS"
    assert result.complete == result.total


def test_check_accepts_a_disagreement_whose_note_runs_several_lines(tmp_path, testset_path):
    note = "the span should stop one character earlier\nsame pattern as row 2"
    answered = _answered_pass(_blank(testset_path)).replace(
        "- [x] agree\n- [ ] disagree\n\nNote:", f"- [ ] agree\n- [x] disagree\n\nNote: {note}", 1
    )
    result = _check(tmp_path, testset_path, answered)
    assert result.ok, result.problems
    disagreements = [q for q in audit.parse_answers(answered) if q.marked == ["disagree"]]
    assert [question.text_of("Note") for question in disagreements] == [note]


def test_check_accepts_a_fail_recorded_before_every_question_is_answered(tmp_path, testset_path):
    failed = (
        _blank(testset_path)
        .replace("- [ ] agree", "- [x] agree", 2)
        .replace("- [ ] FAIL:", "- [x] FAIL:")
        .replace("Reviewer:", "Reviewer: Test Reviewer")
        .replace(f"{audit.DATE_FIELD}:", f"{audit.DATE_FIELD}: {REVIEW_DATE}")
        .replace("Summary:", "Summary: Stopped at row 2; see its note.")
    )
    result = _check(tmp_path, testset_path, failed)
    assert result.ok, result.problems
    assert result.state == "FAIL"


def test_check_accepts_windows_line_endings_and_trailing_spaces(tmp_path, testset_path):
    edited = _answered_pass(_blank(testset_path)).replace("\n", "  \r\n")
    result = _check(tmp_path, testset_path, edited)
    assert result.ok, result.problems
    assert result.state == "PASS"


def test_check_accepts_a_byte_order_mark_before_the_first_line(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, "\ufeff" + _answered_pass(_blank(testset_path)))
    assert result.ok, result.problems
    assert result.state == "PASS"


@pytest.mark.parametrize(
    "box", ["- [x ]", "- [ x]", "- [X]", "- [ X ]", "* [x]", "+ [x]", "- [\uff58]", "- [\uff38]"]
)
def test_check_reads_a_box_marked_with_stray_spaces_a_capital_x_or_another_bullet(
    tmp_path, testset_path, box
):
    result = _check(tmp_path, testset_path, _answered_pass(_blank(testset_path), box=box))
    assert result.ok, result.problems
    assert (result.state, result.complete) == ("PASS", result.total)


@pytest.mark.parametrize("mark", ["\u00d7", "v", "xx", "\u2713"])
def test_check_names_the_line_and_question_of_a_box_it_cannot_read(tmp_path, testset_path, mark):
    blank = _blank(testset_path)
    edited = blank.replace("- [ ] agree", f"- [{mark}] agree", 1)
    result = _check(tmp_path, testset_path, edited)
    assert not result.ok
    where = f"line {_line_number_of(edited, f'- [{mark}] agree')}, {_first_span_location(blank)}"
    assert result.problems == (
        f"{where}: the box before 'agree' holds {mark!r}; replace the space inside [ ] with a "
        "plain x to mark it, or leave it empty",
    )


@pytest.mark.parametrize("verdict", ["none yet", "PASS"])
def test_check_fails_a_note_written_on_the_box_line(tmp_path, testset_path, verdict):
    blank = _blank(testset_path)
    before = blank if verdict == "none yet" else _answered_pass(blank)
    box = "- [ ] agree" if verdict == "none yet" else "- [x] agree"
    edited = before.replace(box, "- [x] agree 邊界可疑", 1)
    result = _check(tmp_path, testset_path, edited)
    assert not result.ok
    where = f"line {_line_number_of(edited, '- [x] agree 邊界可疑')}, {_first_span_location(blank)}"
    assert (
        f"{where}: expected '- [ ] agree', found '- [ ] agree 邊界可疑'; a note goes after Note:"
    ) in "\n".join(result.problems)
    assert any("not agree or disagree" in gap for gap in result.incomplete), result.incomplete


def test_template_mismatch_names_the_file_line_row_and_question(tmp_path, testset_path):
    lines = _answered_pass(_blank(testset_path)).split("\n")
    span_heading = max(i for i, line in enumerate(lines) if line.startswith("### Span "))
    row_heading = max(i for i in range(span_heading) if lines[i].startswith("## Row "))
    marked_text = next(i for i in range(span_heading, len(lines)) if lines[i].startswith("`"))
    lines[marked_text] = lines[marked_text][:-1] + "X`"
    row = re.fullmatch(r"## Row (\d+) of \d+: (\S+)", lines[row_heading])
    span = re.match(r"### Span (\d+) of ", lines[span_heading])
    assert row is not None and span is not None
    result = _check(tmp_path, testset_path, "\n".join(lines))
    assert not result.ok
    where = f"line {marked_text + 1}, row {row.group(1)} ({row.group(2)}), span {span.group(1)}"
    assert f"{where}: expected " in "\n".join(result.problems), result.problems


def test_template_mismatch_reports_a_deleted_option_line_as_missing(tmp_path, testset_path):
    blank = _blank(testset_path)
    edited = blank.replace("- [ ] agree\n- [ ] disagree\n", "- [x] agree\n", 1)
    result = _check(tmp_path, testset_path, edited)
    assert not result.ok
    expected = f"{_first_span_location(blank)}: missing '- [ ] disagree'"
    assert expected in "\n".join(result.problems), result.problems


# The sample table as Prettier 3.7.4 leaves it after formatting AUDIT.md for the
# seed-42 test set: every cell padded to its column width, nothing else changed.
PRETTIER_ALIGNED_TABLE = """\
| Cell                              | Rows in test set | Rows in this sample |
| --------------------------------- | ---------------- | ------------------- |
| ADDRESS: city and district only   | 22               | 3                   |
| ADDRESS: street, ASCII digits     | 50               | 5                   |
| ADDRESS: street, fullwidth digits | 44               | 6                   |
| ORG                               | 99               | 14                  |
| PERSON: 2-character name          | 89               | 10                  |
| PERSON: 3-character name          | 68               | 4                   |
| PERSON: full name + honorific     | 21               | 2                   |
| PERSON: surname + honorific       | 60               | 7                   |
| template: ad_01                   | 19               | 2                   |
| template: ad_02                   | 12               | 1                   |
| template: ad_03                   | 16               | 1                   |
| template: cs_01                   | 17               | 1                   |
| template: cs_02                   | 21               | 2                   |
| template: cs_03                   | 20               | 4                   |
| template: fi_01                   | 22               | 1                   |
| template: fi_02                   | 20               | 2                   |
| template: fi_03                   | 12               | 2                   |
| template: md_01                   | 21               | 2                   |
| template: md_02                   | 17               | 1                   |
| template: neg_01                  | 16               | 3                   |
| template: neg_02                  | 18               | 1                   |
| template: neg_03                  | 16               | 1                   |
| template: rc_01                   | 13               | 1                   |
| template: rc_02                   | 18               | 1                   |
| template: rc_03                   | 22               | 4                   |
| text: punctuation removed         | 98               | 10                  |
| tier: easy                        | 80               | 7                   |
| tier: hard                        | 70               | 8                   |
| tier: medium                      | 100              | 10                  |
| tier: negative                    | 50               | 5                   |
"""
_COMPACT_TABLE_HEADER = "| Cell | Rows in test set | Rows in this sample |"


@pytest.mark.parametrize("answered", [False, True])
def test_check_accepts_the_sample_table_after_prettier_pads_its_columns(
    tmp_path, testset_path, answered
):
    text = _answered_pass(_blank(testset_path)) if answered else _blank(testset_path)
    before_table, header, _ = text.partition(_COMPACT_TABLE_HEADER)
    assert header
    formatted = before_table + PRETTIER_ALIGNED_TABLE
    assert formatted != text
    result = _check(tmp_path, testset_path, formatted)
    assert result.ok, result.problems


def test_check_still_fails_a_padded_table_whose_count_was_edited(tmp_path, testset_path):
    before_table, _, _ = _blank(testset_path).partition(_COMPACT_TABLE_HEADER)
    row = "| ADDRESS: city and district only   | 22               | 3                   |"
    edited_table = PRETTIER_ALIGNED_TABLE.replace(row, row.replace("| 3 ", "| 4 "))
    assert edited_table != PRETTIER_ALIGNED_TABLE
    result = _check(tmp_path, testset_path, before_table + edited_table)
    assert not result.ok
    assert "sample method: expected '| ADDRESS: city and district only | 22 | 3 |'" in (
        "\n".join(result.problems)
    )


def test_check_passes_when_the_changelog_follows_a_completed_pass(tmp_path, testset_path):
    answered = _answered_pass(_blank(testset_path))
    assert _check(tmp_path, testset_path, answered, changelog=True).ok


_TAMPERED_PASSES: dict[str, tuple[Callable[[str], str], str]] = {
    "one span unanswered": (
        lambda text: text.replace("- [x] agree", "- [ ] agree", 1),
        "no box marked",
    ),
    "one unlabeled-entities question unanswered": (
        lambda text: text.replace("- [x] no", "- [ ] no", 1),
        "no box marked",
    ),
    "disagree without a note": (
        lambda text: text.replace("- [x] agree\n- [ ] disagree", "- [ ] agree\n- [x] disagree", 1),
        "needs a note",
    ),
    "yes without a note": (
        lambda text: text.replace("- [x] no\n- [ ] yes", "- [ ] no\n- [x] yes", 1),
        "needs a note",
    ),
    "both boxes of one question marked": (
        lambda text: text.replace("- [x] agree\n- [ ] disagree", "- [x] agree\n- [x] disagree", 1),
        "2 boxes marked",
    ),
    "PASS and FAIL both marked": (
        lambda text: text.replace("- [ ] FAIL:", "- [x] FAIL:"),
        "both marked",
    ),
    "no reviewer": (
        lambda text: text.replace("Reviewer: Test Reviewer", "Reviewer:"),
        "Reviewer",
    ),
    "impossible review date": (
        lambda text: text.replace(REVIEW_DATE, "2026-02-30"),
        "real date",
    ),
    "span offset edited": (
        lambda text: re.sub(r"end=(\d+)", lambda m: f"end={int(m.group(1)) + 1}", text, count=1),
        "does not match its template",
    ),
    "row text edited": (
        lambda text: text.replace("Text: `", "Text: `X", 1),
        "does not match its template",
    ),
}


@pytest.mark.parametrize(
    ("tamper", "expected_problem"), list(_TAMPERED_PASSES.values()), ids=list(_TAMPERED_PASSES)
)
def test_check_fails_a_pass_that_was_tampered_with(
    tmp_path, testset_path, tamper, expected_problem
):
    answered = _answered_pass(_blank(testset_path))
    tampered = tamper(answered)
    assert tampered != answered
    result = _check(tmp_path, testset_path, tampered)
    assert not result.ok
    assert any(expected_problem in problem for problem in result.problems), result.problems


def test_check_fails_a_complete_pass_over_rows_drawn_with_another_seed(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, _answered_pass(_blank(testset_path, seed=7)))
    assert not result.ok
    assert "does not match its template" in result.problems[0]


def test_check_fails_even_an_unanswered_audit_once_test_jsonl_has_changed(tmp_path, testset_path):
    blank = _blank(testset_path)
    generate.write_jsonl(generate.generate_dataset(seed=43), testset_path)
    result = _check(tmp_path, testset_path, blank)
    assert not result.ok
    assert result.problems[0].startswith("the audit was generated for a test set with SHA-256 ")
    assert "make audit-sample FORCE=1" in result.problems[0]


def test_check_fails_when_the_changelog_marks_v0_frozen_but_no_audit_exists(tmp_path, testset_path):
    result = _check(tmp_path, testset_path, None, changelog=True)
    assert not result.ok
    assert "CHANGELOG.md exists" in result.problems[0]


def test_check_fails_when_the_changelog_marks_v0_frozen_during_an_unfinished_audit(
    tmp_path, testset_path
):
    result = _check(tmp_path, testset_path, _blank(testset_path), changelog=True)
    assert not result.ok
    assert "records no PASS" in result.problems[0]


@pytest.mark.parametrize(("make_pass", "exit_code"), [(False, 0), (True, 1)])
def test_check_command_exit_code_is_what_ci_gates_on(
    tmp_path, testset_path, monkeypatch, make_pass, exit_code
):
    """A PASS missing one answer must exit 1; an audit with no verdict yet must exit 0."""
    audit_text = _blank(testset_path)
    if make_pass:
        audit_text = _answered_pass(audit_text).replace("- [x] agree", "- [ ] agree", 1)
    (tmp_path / "AUDIT.md").write_text(audit_text, encoding="utf-8")
    monkeypatch.setattr(audit, "AUDIT_PATH", tmp_path / "AUDIT.md")
    monkeypatch.setattr(audit, "TESTSET_PATH", testset_path)
    monkeypatch.setattr(audit, "CHANGELOG_PATH", tmp_path / "CHANGELOG.md")
    with pytest.raises(SystemExit) as exit_info:
        audit.main(["check"])
    assert exit_info.value.code == exit_code
