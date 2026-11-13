import asyncio
import logging
import random
import re
from dataclasses import dataclass, field

from ..links import clean_url, decorated_url, reel_codes
from ..search.instagram import BLOCKING_ERRORS, Reel
from .examples import STOP, ExampleStore, words
from .generate import Generator
from .model import TZ

log = logging.getLogger(__name__)

FILLER = {"для", "под", "при", "над", "без", "или", "все", "его", "ее"}
MIN_MATCH = 0.5
POOL_SIZE = 15


@dataclass
class Refs:
    urls: list[str] = field(default_factory=list)
    from_base: int = 0
    from_search: int = 0
    searched: bool = False
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.urls:
            parts = []
            if self.from_base:
                parts.append(f"{self.from_base} из ваших примеров ТЗ")
            if self.from_search:
                parts.append(f"{self.from_search} из поиска Instagram")
            lines = ["Референсы: " + ", ".join(parts) + "."]
        else:
            lines = ["Референсы не добавил."]
            if self.searched and not self.notes:
                lines.append("Поиск в Instagram тоже ничего не нашел.")
        lines += self.notes
        if not self.urls:
            lines.append("Добавьте ссылки на рилсы в запрос или повторите позже.")
        return " ".join(lines)


def keys(text: str) -> set[str]:
    return {w[:5] for w in words(text) if len(w) >= 3 and w not in STOP and w not in FILLER}


def match_score(a: str, b: str) -> float:
    ka, kb = keys(a), keys(b)
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def base_codes(store: ExampleStore, product: str, count: int, rng: random.Random) -> list[str]:
    scored = []
    for ex in store.items():
        score = match_score(product, ex.product)
        codes = reel_codes(ex.text)
        if score >= MIN_MATCH and codes:
            scored.append((score, ex.path.name, codes))
    if not scored:
        return []
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    best = scored[0][0]
    top = list(dict.fromkeys(c for s, _, codes in scored if s == best for c in codes))
    rest = list(dict.fromkeys(c for s, _, codes in scored if s != best for c in codes if c not in top))
    rng.shuffle(top)
    return (top + rest)[:count]


def build_pool(reels: dict[str, Reel], need: int, min_views: int) -> list[Reel]:
    best: dict[str, Reel] = {}
    for i, r in enumerate(sorted(reels.values(), key=lambda r: r.views, reverse=True)):
        best.setdefault(r.author or f"#{i}", r)
    ranked = list(best.values())
    known = [r for r in ranked if r.views >= min_views]
    if len(known) < need:
        known += [r for r in ranked if r.views < min_views]
    return known[:POOL_SIZE]


async def live_search(
    ig, generator: Generator, tz: TZ, need: int, min_views: int, exclude: set[str], progress,
) -> list[Reel]:
    queries = tz.references_queries[:3] or [tz.product]
    reels: dict[str, Reel] = {}

    def enough() -> bool:
        return sum(1 for r in reels.values() if r.views >= min_views) >= need * 3

    await progress("Ищу рилсы-референсы..")
    for query in queries:
        for r in await asyncio.to_thread(ig.reels_search, query):
            if r.code not in exclude:
                reels.setdefault(r.code, r)
        if enough():
            break

    if not enough():
        for query in queries[:2]:
            await progress("Ищу через аккаунты..")
            for r in await asyncio.to_thread(ig.account_reels, query, 6):
                if r.code not in exclude:
                    reels.setdefault(r.code, r)
            if enough():
                break

    if not enough():
        glued = [re.sub(r"\W", "", q.lower()) for q in [tz.product] + queries]
        tags = list(dict.fromkeys(tz.references_tags[:3] + [t for t in glued if 3 <= len(t) <= 25]))
        for tag in tags[:5]:
            for r in await asyncio.to_thread(ig.tag_reels, tag):
                if r.code not in exclude:
                    reels.setdefault(r.code, r)
            if enough():
                break

    pool = build_pool(reels, need, min_views)
    log.info("references: %d candidates, pool %d", len(reels), len(pool))
    if not pool:
        return []

    lines = [
        f"{i}. @{r.author} - {r.caption[:150]} (просмотров: {r.views or 'неизвестно'})"
        for i, r in enumerate(pool, start=1)
    ]
    order = await generator.pick_refs(tz.product, ", ".join(queries), lines, need)
    picked = [pool[i] for i in order]
    picked += [r for r in pool if r not in picked]
    return picked[:need]


async def find_references(
    ig, lock: asyncio.Lock, generator: Generator, store: ExampleStore, tz: TZ,
    progress, min_views: int, count: int, tail: bool = True, use_base: bool = False,
) -> Refs:
    rng = random.Random()
    refs = Refs()
    codes = base_codes(store, tz.product, count, rng) if use_base else []
    refs.from_base = len(codes)

    if len(codes) < count and ig is not None:
        if lock.locked():
            refs.notes.append("Поиск блогеров сейчас занят, референсы из Instagram не искал.")
        else:
            refs.searched = True
            async with lock:
                try:
                    found = await live_search(ig, generator, tz, count - len(codes), min_views, set(codes), progress)
                except BLOCKING_ERRORS:
                    ig.reset()
                    found = []
                    refs.notes.append("Сессия Instagram недоступна, референсы из поиска не добавил.")
                except Exception:
                    log.exception("references search failed")
                    found = []
                    refs.notes.append("Поиск референсов в Instagram упал, подробности в логе.")
            codes += [r.code for r in found]
            refs.from_search = len(found)

    refs.urls = [decorated_url(c, rng) if tail else clean_url(c) for c in codes]
    return refs
