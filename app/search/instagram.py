import json
import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    FeedbackRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    RateLimitError,
)

log = logging.getLogger(__name__)

BLOCKING_ERRORS = (LoginRequired, ChallengeRequired, FeedbackRequired, PleaseWaitFewMinutes, RateLimitError)


def collect_users(node, found: dict[str, str]):
    if isinstance(node, dict):
        username = node.get("username")
        pk = node.get("pk") or node.get("pk_id") or node.get("id")
        if isinstance(username, str) and pk and not node.get("is_private"):
            found.setdefault(str(pk), username)
        for value in node.values():
            collect_users(value, found)
    elif isinstance(node, list):
        for value in node:
            collect_users(value, found)

def no_challenge(username, choice):
    raise ChallengeRequired(message="challenge_required")

@dataclass
class Profile:
    pk: str
    username: str
    full_name: str = ""
    followers: int = 0
    category: str = ""
    email: str = ""
    bio: str = ""
    source_tag: str = ""
    reels_count: int = 0
    median_views: int = 0
    avg_views: int = 0
    er: float = 0.0
    last_post: datetime | None = None
    views: list[int] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/{self.username}/"


class Instagram:
    def __init__(
        self,
        settings_path: Path,
        username: str = "",
        password: str = "",
        sessionid: str = "",
        proxy: str = "",
        delay=(2, 5),
        interactive: bool = False,
    ):
        self.settings_path = settings_path
        self.debug_dir = settings_path.parent / "debug"
        self.username = username
        self.password = password
        self.sessionid = sessionid
        self.proxy = proxy
        self.delay = list(delay)
        self.interactive = interactive
        self.client: Client | None = None

    def connect(self) -> Client:
        if self.client:
            return self.client
        cl = Client(delay_range=self.delay)
        if not self.interactive:
            cl.challenge_code_handler = no_challenge
        if self.proxy:
            cl.set_proxy(self.proxy)
        if self.settings_path.exists():
            cl.load_settings(self.settings_path, override_app_version=True)
        cl.set_locale("ru_RU")
        cl.set_country("RU")
        cl.set_country_code(7)
        cl.set_timezone_offset(3 * 3600)
        if self.username and self.password:
            cl.login(self.username, self.password)
        else:
            cl.login_by_sessionid(self.sessionid)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(self.settings_path)
        self.client = cl
        return cl

    def reset(self):
        self.client = None

    def related_tags(self, term: str, top: int = 3) -> list[str]:
        if term.startswith("#"):
            return [term.lstrip("#").lower()]
        base = term.replace(" ", "").lower()
        tags = [base]
        try:
            found = self.connect().search_hashtags(term)
        except BLOCKING_ERRORS:
            raise
        except Exception:
            log.warning("hashtag search failed for %s", term, exc_info=True)
            return tags
        found.sort(key=lambda h: h.media_count or 0, reverse=True)
        for h in found:
            if h.name not in tags:
                tags.append(h.name)
            if len(tags) >= top + 1:
                break
        return tags

    def _request(self, source: str, endpoint: str, **kwargs) -> list[tuple[str, str]]:
        cl = self.connect()
        try:
            payload = cl.private_request(endpoint, **kwargs)
        except BLOCKING_ERRORS:
            raise
        except Exception:
            log.warning("%s failed", source, exc_info=True)
            return []
        users: dict[str, str] = {}
        collect_users(payload, users)
        users.pop(str(cl.user_id), None)
        log.info("%s: %d authors", source, len(users))
        if not users:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^\w-]+", "_", source)[:80]
            (self.debug_dir / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return list(users.items())

    def reels_authors(self, query: str) -> list[tuple[str, str]]:
        cl = self.connect()
        params = {"search_surface": "clips_search_page", "timezone_offset": cl.timezone_offset, "query": query}
        return self._request(f"reels {query}", "fbsearch/reels_serp/", params=params)

    def account_authors(self, query: str) -> list[tuple[str, str]]:
        cl = self.connect()
        params = {"search_surface": "account_serp", "timezone_offset": cl.timezone_offset, "query": query}
        return self._request(f"accounts {query}", "fbsearch/account_serp/", params=params)

    def tag_authors(self, tag: str) -> list[tuple[str, str]]:
        cl = self.connect()
        result = []
        for tab, recency in (("clips", "clips"), ("top", "default")):
            data = {
                "tab": tab,
                "media_recency_filter": recency,
                "_uuid": cl.uuid,
                "include_persistent": "false",
                "rank_token": cl.rank_token,
            }
            result += self._request(f"tag {tag} {tab}", f"tags/{tag}/sections/", data=data, with_signature=False)
        return result

    def profile(self, pk: str) -> Profile | None:
        u = self.connect().user_info_v1(pk)
        if u.is_private:
            return None
        return Profile(
            pk=str(u.pk),
            username=u.username,
            full_name=u.full_name or "",
            followers=u.follower_count or 0,
            category=u.category_name or u.category or u.business_category_name or "",
            email=u.public_email or "",
            bio=(u.biography or "").replace("\n", " "),
        )

    def fill_reels(self, p: Profile, amount: int = 12) -> Profile:
        medias, _ = self.connect().user_medias_paginated_v1(p.pk, amount=24)
        clips = [m for m in medias if m.product_type == "clips" or (m.media_type == 2 and (m.play_count or m.view_count))]
        clips = clips[:amount]
        views = [c.play_count or c.view_count or 0 for c in clips]
        views = [v for v in views if v > 0]
        p.reels_count = len(clips)
        p.views = views
        if views:
            p.median_views = int(statistics.median(views))
            p.avg_views = int(statistics.mean(views))
        if clips and p.followers:
            eng = [(c.like_count or 0) + (c.comment_count or 0) for c in clips]
            p.er = round(statistics.mean(eng) / p.followers * 100, 2)
        dates = [c.taken_at for c in clips if c.taken_at]
        p.last_post = max(dates) if dates else None
        return p