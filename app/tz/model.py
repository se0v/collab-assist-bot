import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "defaults.json"


@dataclass
class TZ:
    brand: str = ""
    product: str = ""
    title: str = ""
    subtitle: str = ""
    conditions: list[str] = field(default_factory=list)
    theses_intro: str = ""
    theses: list[str] = field(default_factory=list)
    examples_note: str = ""
    references: list[str] = field(default_factory=list)


def load_defaults() -> dict:
    with open(DEFAULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def apply_defaults(tz: TZ, default_brand: str = "") -> TZ:
    d = load_defaults()
    tz.brand = (tz.brand or default_brand).strip()
    brand = tz.brand or "бренда"

    tz.title = tz.title or d["title"]
    tz.subtitle = tz.subtitle or d["subtitle"]
    if not tz.conditions:
        tz.conditions = [c.replace("{brand}", brand) for c in d["conditions"]]
    if not tz.examples_note:
        tz.examples_note = d["examples_note"].replace("{brand}", brand)
    return tz