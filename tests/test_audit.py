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


def _answered_pass(blank: str) -> str:
    """Answer every span agree and every row no, then record a signed PASS."""
    return (
        blank.replace("- [ ] agree", "- [x] agree")
        .replace("- [ ] no", "- [x] no")
        .replace("- [ ] PASS:", "- [x] PASS:")
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
        "differs from the template",
    ),
    "row text edited": (
        lambda text: text.replace("Text: `", "Text: `X", 1),
        "differs from the template",
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
    assert "differs from the template" in result.problems[0]


def test_check_fails_even_an_unanswered_audit_once_test_jsonl_has_changed(tmp_path, testset_path):
    blank = _blank(testset_path)
    generate.write_jsonl(generate.generate_dataset(seed=43), testset_path)
    result = _check(tmp_path, testset_path, blank)
    assert not result.ok
    assert "SHA-256" in result.problems[0]


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
