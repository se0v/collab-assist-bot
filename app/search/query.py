import re
from dataclasses import dataclass, field

NUM = r"(\d+(?:[.,]\d+)?)\s*(к|k|тыс\.?|м|m|млн\.?)?"
MULT = {"к": 1_000, "k": 1_000, "тыс": 1_000, "м": 1_000_000, "m": 1_000_000, "млн": 1_000_000}

FIELDS = {
    "followers": re.compile(r"^(подписчик\w*|подп\w*|фолловер\w*)\s*:?\s*(.+)$", re.I),
    "views": re.compile(r"^(просмотр\w*|просм\w*)\s*:?\s*(.+)$", re.I),
    "limit": re.compile(r"^(лимит|профил\w*|количество)\s*:?\s*(\d+)$", re.I),
}


@dataclass
class Range:
    low: int | None = None
    high: int | None = None

    def __contains__(self, value: int) -> bool:
        if self.low is not None and value < self.low:
            return False
        if self.high is not None and value > self.high:
            return False
        return True

    def __str__(self) -> str:
        if self.low is None and self.high is None:
            return "любые"
        if self.high is None:
            return f"от {human(self.low)}"
        if self.low is None:
            return f"до {human(self.high)}"
        return f"{human(self.low)}–{human(self.high)}"


@dataclass
class SearchQuery:
    terms: list[str] = field(default_factory=list)
    followers: Range = field(default_factory=Range)
    views: Range = field(default_factory=Range)
    limit: int = 30


def human(n: int | float | None) -> str:
    if n is None:
        return "-"
    for size, word in ((1_000_000, "млн"), (1_000, "тыс")):
        if n >= size:
            value = f"{n / size:.1f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"{value} {word}"
    return str(int(n))


def to_int(num: str, suffix: str | None) -> int:
    value = float(num.replace(",", "."))
    if suffix:
        value *= MULT[suffix.lower().rstrip(".")]
    return int(value)


def parse_range(text: str) -> Range:
    text = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", text.lower())
    nums = [to_int(n, s) for n, s in re.findall(NUM, text)]
    if not nums:
        return Range()
    if len(nums) >= 2:
        return Range(min(nums[:2]), max(nums[:2]))
    if re.search(r"\bдо\b|<|не более|максимум", text):
        return Range(high=nums[0])
    return Range(low=nums[0])


def parse_query(text: str, default_limit: int = 30) -> SearchQuery:
    q = SearchQuery(limit=default_limit)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        for name, rx in FIELDS.items():
            m = rx.match(line)
            if m:
                if name == "limit":
                    q.limit = max(1, min(int(m.group(2)), 100))
                else:
                    setattr(q, name, parse_range(m.group(2)))
                break
        else:
            q.terms += [t.strip() for t in re.split(r"[,;]", line) if t.strip()]
    return q