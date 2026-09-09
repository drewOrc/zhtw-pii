"""Deterministic synthetic zh-TW PII dataset generator (v0).

Builds sentences from hand-written templates, filling PERSON, ADDRESS, and
ORG slots with synthetic values drawn from small public-statistic lexicons.
Nothing here reads or writes any real individual's data.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_LEXICON_DIR = Path(__file__).parent / "lexicon"

ENTITY_LABELS: frozenset[str] = frozenset({"PERSON", "ADDRESS", "ORG"})
TOKEN_PATTERN = re.compile(r"\{([A-Z_]+)\}")
DEFAULT_TIER_COUNTS: dict[str, int] = {"easy": 80, "medium": 100, "hard": 70, "negative": 50}
MAX_BLOCKLIST_ATTEMPTS = 50

_FULLWIDTH_OFFSET = 0xFEE0
_STRIPPED_CHARS = frozenset(" \t，。：；、！？,.:;!?")

GIVEN_NAME_CHARS: tuple[str, ...] = (
    "家",
    "文",
    "宇",
    "翔",
    "傑",
    "豪",
    "偉",
    "明",
    "智",
    "勇",
    "浩",
    "軒",
    "翊",
    "佳",
    "怡",
    "雅",
    "婷",
    "淑",
    "惠",
    "玲",
    "靜",
    "筠",
    "柔",
    "涵",
    "昀",
    "詩",
    "嘉",
    "彥",
    "承",
    "品",
    "恩",
    "宸",
    "睿",
    "芸",
    "瑄",
    "語",
    "心",
    "詠",
    "采",
    "岑",
    "小",
)
HONORIFICS: tuple[str, ...] = ("先生", "小姐", "女士")

CITIES: dict[str, tuple[str, ...]] = {
    "台北市": ("中正區", "大安區", "信義區", "士林區"),
    "新北市": ("板橋區", "三重區", "中和區", "新莊區"),
    "桃園市": ("桃園區", "中壢區", "八德區"),
    "台中市": ("西屯區", "北屯區", "南屯區"),
    "台南市": ("東區", "北區", "安平區"),
    "高雄市": ("三民區", "苓雅區", "鳳山區"),
    "新竹市": ("東區", "北區"),
    "基隆市": ("仁愛區", "信義區"),
}
ROAD_NAME_PARTS: tuple[str, ...] = (
    "中山",
    "中正",
    "忠孝",
    "仁愛",
    "信義",
    "和平",
    "民生",
    "建國",
    "復興",
    "羅斯福",
)
ROAD_SUFFIXES: tuple[str, ...] = ("路", "街")

ORG_PREFIX_WORDS: tuple[str, ...] = (
    "誠信",
    "昇陽",
    "啟明",
    "華夏",
    "匯通",
    "立信",
    "協和",
    "廣益",
    "集賢",
    "泰安",
)
ORG_SUFFIXES: tuple[str, ...] = (
    "股份有限公司",
    "有限公司",
    "診所",
    "事務所",
    "工作室",
    "基金會",
    "協會",
)


@dataclass(frozen=True)
class Entity:
    """A single labeled character span within an example's text."""

    start: int
    end: int
    label: str

    def to_json_dict(self) -> dict[str, int | str]:
        """Return the plain-dict form used for JSONL serialization."""
        return {"start": self.start, "end": self.end, "label": self.label}


@dataclass(frozen=True)
class Example:
    """One generated dataset row."""

    id: str
    text: str
    entities: list[Entity]
    tier: str
    seed: int
    template_id: str

    def to_json_dict(self) -> dict[str, object]:
        """Return the plain-dict form used for JSONL serialization."""
        return {
            "id": self.id,
            "text": self.text,
            "entities": [entity.to_json_dict() for entity in self.entities],
            "tier": self.tier,
            "seed": self.seed,
            "template_id": self.template_id,
        }


@dataclass(frozen=True)
class Template:
    """A sentence frame with `{TOKEN}` placeholders for entities and filler."""

    id: str
    scenario: str
    text: str

    @property
    def entity_count(self) -> int:
        """Number of PERSON/ADDRESS/ORG placeholders in this template."""
        return sum(1 for token in TOKEN_PATTERN.findall(self.text) if token in ENTITY_LABELS)


@dataclass(frozen=True)
class NoiseProfile:
    """Which noise transforms are active for one generated row."""

    strip_punctuation: bool
    honorific: bool
    fullwidth: bool
    partial_address: bool


TEMPLATES: tuple[Template, ...] = (
    Template("cs_01", "customer_service", "您好，我是{PERSON}，想詢問訂單狀態。"),
    Template(
        "cs_02", "customer_service", "客戶{PERSON}來電反映，居住地址為{ADDRESS}，請盡快處理。"
    ),
    Template(
        "cs_03", "customer_service", "{PERSON}的包裹已送達{ADDRESS}，如有疑問請聯繫{ORG}客服。"
    ),
    Template("ad_01", "admin", "申請人：{PERSON}。"),
    Template("ad_02", "admin", "本案由{ORG}承辦，聯絡人為{PERSON}。"),
    Template("ad_03", "admin", "{PERSON}的戶籍地址登記為{ADDRESS}，特此公告。"),
    Template("fi_01", "finance", "匯款人{PERSON}，請確認收款帳戶無誤。"),
    Template("fi_02", "finance", "{ORG}已將款項匯至{PERSON}的帳戶，地址核對為{ADDRESS}。"),
    Template("fi_03", "finance", "本月請款單位：{ORG}。"),
    Template("md_01", "medical", "病患{PERSON}預約於明日回診。"),
    Template("md_02", "medical", "{PERSON}的聯絡地址為{ADDRESS}，看診科別為家醫科。"),
    Template("rc_01", "recruiting", "應徵者{PERSON}投遞了{ORG}的職缺。"),
    Template("rc_02", "recruiting", "姓名：{PERSON}。"),
    Template("rc_03", "recruiting", "{ORG}人資部門將聯繫{PERSON}安排面試，地點：{ADDRESS}。"),
    Template("neg_01", "logistics", "訂單編號{ORDER_NO}已出貨，預計{DATE}送達，金額{AMOUNT}。"),
    Template("neg_02", "logistics", "本次活動日期為{DATE}，報名人數上限{NUMBER}人，費用{AMOUNT}。"),
    Template("neg_03", "logistics", "產品編號{PRODUCT_CODE}，庫存數量{NUMBER}件，到貨日{DATE}。"),
)

TEMPLATE_POOLS: dict[str, tuple[Template, ...]] = {
    "easy": tuple(t for t in TEMPLATES if t.entity_count == 1),
    "medium": tuple(t for t in TEMPLATES if t.entity_count >= 2),
    "hard": tuple(t for t in TEMPLATES if t.entity_count >= 1),
    "negative": tuple(t for t in TEMPLATES if t.entity_count == 0),
}

_NOISE_PROBABILITY: dict[str, dict[str, float]] = {
    "easy": {"strip": 0.0, "honorific": 0.0, "fullwidth": 0.0, "partial_address": 0.0},
    "medium": {"strip": 0.4, "honorific": 0.4, "fullwidth": 0.4, "partial_address": 0.0},
    "hard": {"strip": 0.8, "honorific": 0.7, "fullwidth": 0.8, "partial_address": 0.6},
    "negative": {"strip": 0.15, "honorific": 0.0, "fullwidth": 0.3, "partial_address": 0.0},
}


def _read_word_list(path: Path) -> list[str]:
    """Read one non-empty, non-comment entry per line from a text file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


SURNAMES: tuple[str, ...] = tuple(_read_word_list(_LEXICON_DIR / "surnames.txt"))


def load_blocklist(path: Path | None = None) -> set[str]:
    """Load blocked full names, defaulting to the bundled lexicon file."""
    target = path if path is not None else _LEXICON_DIR / "blocklist.txt"
    return set(_read_word_list(target))


def to_fullwidth(text: str) -> str:
    """Convert ASCII digits and punctuation in text to their fullwidth forms."""
    converted = []
    for char in text:
        code = ord(char)
        if char == " ":
            converted.append("　")
        elif 0x21 <= code <= 0x7E:
            converted.append(chr(code + _FULLWIDTH_OFFSET))
        else:
            converted.append(char)
    return "".join(converted)


def strip_spaces_and_punctuation(text: str) -> str:
    """Remove spaces and common punctuation, simulating unformatted input."""
    return "".join(char for char in text if char not in _STRIPPED_CHARS)


def _sample_noise_profile(rng: random.Random, tier: str) -> NoiseProfile:
    """Roll which noise transforms apply to one row, based on tier difficulty."""
    probabilities = _NOISE_PROBABILITY[tier]
    return NoiseProfile(
        strip_punctuation=rng.random() < probabilities["strip"],
        honorific=rng.random() < probabilities["honorific"],
        fullwidth=rng.random() < probabilities["fullwidth"],
        partial_address=rng.random() < probabilities["partial_address"],
    )


def _generate_blocklist_safe_base_name(rng: random.Random, blocklist: set[str]) -> str:
    """Sample a surname plus given-name combo that is not in the blocklist."""
    for _ in range(MAX_BLOCKLIST_ATTEMPTS):
        surname = rng.choice(SURNAMES)
        given_name_length = rng.choice((1, 2))
        given_name = "".join(rng.choice(GIVEN_NAME_CHARS) for _ in range(given_name_length))
        candidate = f"{surname}{given_name}"
        if candidate not in blocklist:
            return candidate
    raise RuntimeError("could not sample a name outside the blocklist; blocklist too broad")


def generate_person(rng: random.Random, blocklist: set[str], profile: NoiseProfile) -> str:
    """Generate a synthetic person name, honoring the blocklist and noise profile."""
    base = _generate_blocklist_safe_base_name(rng, blocklist)
    if not profile.honorific:
        return base
    honorific = rng.choice(HONORIFICS)
    if rng.random() < 0.7:
        return f"{base[0]}{honorific}"
    return f"{base}{honorific}"


def generate_address(rng: random.Random, profile: NoiseProfile) -> str:
    """Generate a synthetic Taiwan-style address, to district or full street."""
    city = rng.choice(list(CITIES))
    district = rng.choice(CITIES[city])
    address = f"{city}{district}"
    if not profile.partial_address:
        road = rng.choice(ROAD_NAME_PARTS)
        suffix = rng.choice(ROAD_SUFFIXES)
        section = rng.randint(1, 3)
        number = rng.randint(1, 300)
        address += f"{road}{suffix}{section}段{number}號"
    return to_fullwidth(address) if profile.fullwidth else address


def generate_org(rng: random.Random) -> str:
    """Generate a synthetic organization name from a prefix and legal suffix."""
    prefix = rng.choice(ORG_PREFIX_WORDS)
    suffix = rng.choice(ORG_SUFFIXES)
    return f"{prefix}{suffix}"


def generate_filler(token: str, rng: random.Random, profile: NoiseProfile) -> str:
    """Generate non-entity filler text for the negative tier's number-dense tokens."""
    if token == "DATE":
        value = f"{rng.randint(2024, 2026)}年{rng.randint(1, 12):02d}月{rng.randint(1, 28):02d}日"
    elif token == "AMOUNT":
        value = f"NT${rng.randint(100, 99999):,}"
    elif token == "ORDER_NO":
        value = f"{rng.choice('ABCDEFGH')}{rng.randint(10**8, 10**9 - 1)}"
    elif token == "PRODUCT_CODE":
        value = f"P{rng.randint(1000, 9999)}-{rng.choice('ABCDEFGH')}"
    elif token == "NUMBER":
        value = str(rng.randint(1, 500))
    else:
        raise ValueError(f"unknown filler token: {token}")
    return to_fullwidth(value) if profile.fullwidth else value


def _generate_entity_value(
    label: str, rng: random.Random, blocklist: set[str], profile: NoiseProfile
) -> str:
    """Dispatch to the generator for a single entity label."""
    if label == "PERSON":
        return generate_person(rng, blocklist, profile)
    if label == "ADDRESS":
        return generate_address(rng, profile)
    if label == "ORG":
        return generate_org(rng)
    raise ValueError(f"unknown entity label: {label}")


def render_template(
    template: Template, rng: random.Random, tier: str, blocklist: set[str]
) -> tuple[str, list[Entity]]:
    """Fill a template's placeholders and return the text with entity spans.

    Entity spans are computed by construction while appending each piece, so
    they stay exact no matter which noise transforms fire for this row.
    """
    profile = _sample_noise_profile(rng, tier)
    parts = TOKEN_PATTERN.split(template.text)
    chunks: list[str] = []
    entities: list[Entity] = []
    cursor = 0
    for index, part in enumerate(parts):
        if index % 2 == 0:
            literal = strip_spaces_and_punctuation(part) if profile.strip_punctuation else part
            chunks.append(literal)
            cursor += len(literal)
            continue
        token = part
        if token in ENTITY_LABELS:
            value = _generate_entity_value(token, rng, blocklist, profile)
            entities.append(Entity(start=cursor, end=cursor + len(value), label=token))
        else:
            value = generate_filler(token, rng, profile)
        chunks.append(value)
        cursor += len(value)
    return "".join(chunks), entities


def generate_dataset(
    seed: int,
    tier_counts: Mapping[str, int] | None = None,
    blocklist: set[str] | None = None,
) -> list[Example]:
    """Generate a deterministic synthetic PII dataset for the given seed.

    The same seed and tier_counts always produce byte-identical output: every
    random draw comes from a single random.Random instance seeded here, never
    from the global random module.
    """
    counts = dict(tier_counts) if tier_counts is not None else dict(DEFAULT_TIER_COUNTS)
    active_blocklist = blocklist if blocklist is not None else load_blocklist()
    rng = random.Random(seed)
    examples: list[Example] = []
    for tier in ("easy", "medium", "hard", "negative"):
        pool = TEMPLATE_POOLS[tier]
        for index in range(counts.get(tier, 0)):
            template = rng.choice(pool)
            text, entities = render_template(template, rng, tier, active_blocklist)
            examples.append(
                Example(
                    id=f"{tier}_{index + 1:03d}",
                    text=text,
                    entities=entities,
                    tier=tier,
                    seed=seed,
                    template_id=template.id,
                )
            )
    return examples


def write_jsonl(examples: Iterable[Example], path: Path) -> None:
    """Write examples as JSONL, one compact JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example.to_json_dict(), ensure_ascii=False))
            handle.write("\n")


def parse_tier_counts(spec: str) -> dict[str, int]:
    """Parse a 'tier=count,tier=count' string into a tier count mapping."""
    counts: dict[str, int] = {}
    for item in spec.split(","):
        tier, _, count = item.partition("=")
        if not tier or not count:
            raise ValueError(f"invalid tier count entry: {item!r}")
        counts[tier.strip()] = int(count.strip())
    return counts


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for `python -m zhtw_pii.data.generate`."""
    parser = argparse.ArgumentParser(description="Generate the synthetic zhtw-pii dataset.")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/testset/v0/test.jsonl"),
        help="output JSONL path",
    )
    parser.add_argument(
        "--tier-counts",
        type=parse_tier_counts,
        default=None,
        help="override tier counts, e.g. 'easy=80,medium=100,hard=70,negative=50'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for `python -m zhtw_pii.data.generate`."""
    args = build_arg_parser().parse_args(argv)
    examples = generate_dataset(seed=args.seed, tier_counts=args.tier_counts)
    write_jsonl(examples, args.out)
    print(f"wrote {len(examples)} examples to {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()
