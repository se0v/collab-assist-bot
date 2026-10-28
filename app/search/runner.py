import asyncio
import logging
from collections.abc import Awaitable, Callable

from .instagram import BLOCKING_ERRORS, Instagram, Profile
from .query import SearchQuery

log = logging.getLogger(__name__)

Progress = Callable[[str], Awaitable[None]]


class SearchStopped(Exception):
    def __init__(self, reason: str, found: list[Profile]):
        super().__init__(reason)
        self.reason = reason
        self.found = found


async def run_search(ig: Instagram, q: SearchQuery, progress: Progress, max_checks: int = 80) -> list[Profile]:
    found: list[Profile] = []
    try:
        candidates: dict[str, tuple[str, str]] = {}

        def add(items: list[tuple[str, str]], source: str):
            for pk, username in items:
                candidates.setdefault(pk, (username, source))

        for term in q.terms:
            if term.startswith("#"):
                tag = term.lstrip("#").lower()
                await progress(f"Смотрю хештег #{tag}..")
                add(await asyncio.to_thread(ig.tag_authors, tag), "#" + tag)
                continue

            await progress(f"Ищу рилсы по запросу «{term}»..")
            add(await asyncio.to_thread(ig.reels_authors, term), "рилсы: " + term)
            await progress(f"Ищу аккаунты по запросу «{term}»..")
            add(await asyncio.to_thread(ig.account_authors, term), "аккаунты: " + term)
            for tag in await asyncio.to_thread(ig.related_tags, term, 1):
                await progress(f"Смотрю хештег #{tag}..")
                add(await asyncio.to_thread(ig.tag_authors, tag), "#" + tag)

        total = min(len(candidates), max_checks)
        await progress(f"Авторов найдено: {len(candidates)}. Проверяю {total}..")

        for i, (pk, (username, tag)) in enumerate(list(candidates.items())[:total], start=1):
            try:
                p = await asyncio.to_thread(ig.profile, pk)
                if p is None or p.followers not in q.followers:
                    continue
                p.source_tag = tag
                await asyncio.to_thread(ig.fill_reels, p)
                if p.median_views in q.views:
                    found.append(p)
            except BLOCKING_ERRORS:
                raise
            except Exception:
                log.warning("profile %s failed", username, exc_info=True)
            if i % 5 == 0 or i == total:
                await progress(f"Проверено {i} из {total}, подходят: {len(found)}")
            if len(found) >= q.limit:
                break
    except BLOCKING_ERRORS as e:
        ig.reset()
        raise SearchStopped(type(e).__name__, sorted_profiles(found)) from e

    return sorted_profiles(found)


def sorted_profiles(profiles: list[Profile]) -> list[Profile]:
    return sorted(profiles, key=lambda p: p.median_views, reverse=True)