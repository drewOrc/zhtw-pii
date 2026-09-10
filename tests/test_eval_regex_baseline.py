"""Unit tests for the zero-dependency regex baseline.

Several cases here pin *documented weaknesses*, not bugs: this baseline is
supposed to be a naive lower bound (see the module docstring in
`zhtw_pii/eval/baselines/regex_rules.py` and `docs/adr/0002`), so a test
that only accepted clean matches would hide regressions in the other
direction (the baseline quietly becoming smarter than it claims to be,
which would make it an unfair sanity floor).
"""

import pytest

from zhtw_pii.eval.baselines.regex_rules import (
    COUNTIES_AND_CITIES,
    TOP100_SURNAMES,
    RegexBaseline,
    predict_spans,
)
from zhtw_pii.eval.types import BaselineMetadata

pytestmark = pytest.mark.unit


def _labels_and_text(sentence: str) -> set[tuple[str, str]]:
    return {(span.label, sentence[span.start : span.end]) for span in predict_spans(sentence)}


def test_person_with_two_character_given_name():
    assert _labels_and_text("姓名：林知遠。") == {("PERSON", "林知遠")}


def test_person_honorific_with_zero_given_name_characters():
    """ "王先生" has no given name at all: surname plus a mandatory honorific."""
    assert _labels_and_text("王先生您好，這是您的收據。") == {("PERSON", "王先生")}


def test_person_honorific_with_single_base_character():
    assert _labels_and_text("陳小姐正在等候叫號。") == {("PERSON", "陳小姐")}


def test_address_consumes_fullwidth_digits_in_the_street_number():
    result = _labels_and_text("聯絡地址：高雄市三民區建國路３段８號。")
    assert ("ADDRESS", "高雄市三民區建國路３段８號") in result


def test_address_matches_district_only_when_no_street_follows():
    assert _labels_and_text("客戶居住於台中市西屯區，請協助確認。") == {("ADDRESS", "台中市西屯區")}


def test_org_bleeds_backward_across_a_punctuation_free_prefix():
    """Documented limitation: no punctuation boundary before the org name.

    `\\S`-style prefix matching (here, non-punctuation matching) has no
    way to tell "本案由" (filler) apart from the company name that
    follows it once nothing separates them; see the design-deviations
    note in regex_rules.py.
    """
    assert _labels_and_text("本案由誠信協會處理。") == {("ORG", "本案由誠信協會")}


def test_org_matches_cleanly_when_nothing_precedes_it():
    assert _labels_and_text("誠信協會提供法律諮詢。") == {("ORG", "誠信協會")}


def test_org_prefix_does_not_cross_a_preceding_comma():
    """The punctuation-boundary fix: a full-width comma stops backward bleed."""
    assert _labels_and_text("已確認，誠信協會將於明日回覆。") == {("ORG", "誠信協會")}


def test_person_given_name_bleeds_forward_into_a_real_word_without_a_stoplist():
    """Pinned from data/testset/v0/test.jsonl id=hard_001.

    Gold PERSON is "楊嘉" (span 0-2); the given-name character class has
    no stoplist, so it greedily absorbs "的" as a second given-name
    character. ADDRESS on the same sentence is unaffected and exact.
    """
    result = _labels_and_text("楊嘉的戶籍地址登記為台南市北區特此公告")
    assert ("PERSON", "楊嘉的") in result
    assert ("ADDRESS", "台南市北區") in result


def test_surname_character_collides_with_a_place_name_prefix():
    """ "高" is both a real surname and the first character of "高雄".

    This is the project plan's own canonical example of why PERSON is not
    solvable by regex (internal/PLAN.md section 4.1); the false PERSON
    match on "高雄市" here is that ambiguity actually firing.
    """
    result = _labels_and_text("聯絡地址：高雄市三民區建國路３段８號。")
    assert ("PERSON", "高雄市") in result


def test_common_word_false_positives_as_person_when_it_starts_with_a_surname_character():
    """ "金額" (amount) false-positives as PERSON because "金" is a real surname.

    This is the single recurring cause of every negative-tier false
    positive this baseline produces on the v0 test set (see
    docs/benchmark.md's Limitations section).
    """
    result = _labels_and_text("訂單編號A12345已出貨，預計2025年01月01日送達，金額NT$500。")
    assert ("PERSON", "金額") in result


def test_no_entities_predicted_for_a_sentence_with_none_of_the_lexicon_triggers():
    assert predict_spans("今天天氣晴朗，適合出門散步。") == []


def test_top100_surnames_is_a_strict_superset_of_the_generators_surname_lexicon():
    """Documents the known overlap called out in docs/benchmark.md's Limitations."""
    from zhtw_pii.data.generate import SURNAMES

    assert set(SURNAMES).issubset(set(TOP100_SURNAMES))
    assert len(TOP100_SURNAMES) == 100


def test_counties_and_cities_lists_all_22_taiwan_top_level_divisions():
    assert len(COUNTIES_AND_CITIES) == 22
    assert len(set(COUNTIES_AND_CITIES)) == 22


def test_load_reports_no_model_file_and_data_never_leaves_the_machine():
    metadata = RegexBaseline().load()
    assert isinstance(metadata, BaselineMetadata)
    assert metadata.size_mb is None
    assert metadata.data_leaves_machine is False
    assert metadata.bytes_sent is None


def test_predict_spans_are_sorted_by_start_position():
    spans = predict_spans("陳先生的地址是台北市大安區，服務單位為誠信協會。")
    starts = [span.start for span in spans]
    assert starts == sorted(starts)
