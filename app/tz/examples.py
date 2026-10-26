import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

WORD = re.compile(r"[a-zа-я0-9]+")
STOP = {
    "нужно", "нужен", "нужна", "сделай", "сделать", "напиши", "пожалуиста", "пришли",
    "товар", "товара", "бренд", "бренда", "для", "мне", "нам", "это", "как", "что", "про",
}
MAX_CHARS = 3000


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower().replace("ё", "е").replace("й", "и"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return WORD.findall(text)


def stem(word: str) -> str:
    return word if len(word) <= 4 else word[: max(4, len(word) - 2)]


def hits(query: list[str], target: list[str]) -> int:
    return sum(any(t.startswith(stem(q)) for t in target) for q in query)


@dataclass
class Example:
    path: Path
    product: str
    text: str

    @property
    def short(self) -> str:
        return self.text[:MAX_CHARS]


class ExampleStore:
    def __init__(self, folder: Path):
        self.folder = folder

    def items(self) -> list[Example]:
        if not self.folder.exists():
            return []
        result = []
        for path in sorted(self.folder.glob("*.txt")):
            head, _, body = path.read_text(encoding="utf-8").partition("\n")
            result.append(Example(path, head.removeprefix("Товар:").strip(), body.strip()))
        return result

    def add(self, product: str, text: str) -> Example:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{int(time.time() * 1000)}.txt"
        path.write_text(f"Товар: {product}\n{text.strip()}\n", encoding="utf-8")
        return Example(path, product, text.strip())

    def delete(self, number: int) -> Example | None:
        items = self.items()
        if not 1 <= number <= len(items):
            return None
        item = items[number - 1]
        item.path.unlink()
        return item

    def pick(self, request: str, limit: int = 3) -> list[Example]:
        query = [w for w in words(request) if len(w) >= 3 and w not in STOP]
        scored = []
        for i, ex in enumerate(self.items()):
            score = hits(query, words(ex.product)) * 10 + min(hits(query, words(ex.text)), 5)
            scored.append((score, i, ex))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [ex for _, _, ex in scored[:limit]]