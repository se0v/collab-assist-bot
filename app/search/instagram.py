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

from ..links import clean_url, code_from_pk

log = logging.getLogger(__name__)

BLOCKING_ERRORS = (LoginRequired, ChallengeRequired, FeedbackRequired, PleaseWaitFewMinutes, RateLimitError)

CODE = re.compile(r"^[A-Za-z0-9_-]{5,20}$")
VIEW_KEYS = ("play_count", "view_count", "ig_play_count", "video_view_count")
MEDIA_KEYS = ("pk", "id", "media_type", "product_type", "taken_at", "play_count", "video_versions", "clips_metadata")


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


@dataclass
class Reel:
    code: str
    views: int = 0
    author: str = ""
    caption: str = ""

    @property
    def url(self) -> str:
        return clean_url(self.code)


def to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def media_code(node: dict) -> str:
    code = node.get("code")
    if isinstance(code, str) and CODE.match(code):
        return code
    if node.get("media_type") is None and node.get("product_type") is None:
        return ""
    pk = str(node.get("pk") or node.get("id") or "").split("_")[0]
    if pk.isdigit() and len(pk) >= 15:
        return code_from_pk(pk)
    return ""


def collect_media(node, found: dict[str, Reel]):
    if isinstance(node, dict):
        code = media_code(node)
        is_media = code and any(key in node for key in MEDIA_KEYS)
        if is_media and node.get("media_type") not in (1, 8):
            user = node.get("user")
            caption = node.get("caption")
            if isinstance(caption, dict):
                caption = caption.get("text")
            found.setdefault(code, Reel(
                code=code,
                views=max(to_int(node.get(key)) for key in VIEW_KEYS),
                author=str(user.get("username") or "") if isinstance(user, dict) else "",
                caption=str(caption or "").replace("\n", " "),
            ))
        for value in node.values():
            collect_media(value, found)
    elif isinstance(node, list):
        for value in node:
            collect_media(value, found)


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
        elif self.sessionid:
            cl.login_by_sessionid(self.sessionid)
        elif not cl.user_id:
            raise LoginRequired(message="login_required")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(self.settings_path)
        self.client = cl
        return cl

    def reset(self):
        self.client = None

    def _dump(self, source: str, payload):
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w-]+", "_", source)[:80]
        (self.debug_dir / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

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
            self._dump(source, payload)
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

    def _reels_request(self, source: str, endpoint: str, **kwargs) -> list[Reel]:
        cl = self.connect()
        try:
            payload = cl.private_request(endpoint, **kwargs)
        except BLOCKING_ERRORS:
            raise
        except Exception:
            log.warning("%s failed", source, exc_info=True)
            return []
        found: dict[str, Reel] = {}
        collect_media(payload, found)
        reels = list(found.values())
        log.info("%s: %d reels, %d with views", source, len(reels), sum(1 for r in reels if r.views))
        if not reels:
            self._dump(f"refs {source}", payload)
        return reels

    def reels_search(self, query: str) -> list[Reel]:
        cl = self.connect()
        params = {"search_surface": "clips_search_page", "timezone_offset": cl.timezone_offset, "query": query}
        return self._reels_request(f"reels {query}", "fbsearch/reels_serp/", params=params)

    def tag_reels(self, tag: str) -> list[Reel]:
        cl = self.connect()
        data = {
            "tab": "clips",
            "media_recency_filter": "clips",
            "_uuid": cl.uuid,
            "include_persistent": "false",
            "rank_token": cl.rank_token,
        }
        reels = self._reels_request(f"tag {tag}", f"tags/{tag}/sections/", data=data, with_signature=False)
        if reels:
            return reels
        try:
            medias = cl.hashtag_medias_reels_v1(tag, amount=30)
        except BLOCKING_ERRORS:
            raise
        except Exception:
            log.warning("tag %s fallback failed", tag, exc_info=True)
            return []
        reels = [
            Reel(
                code=m.code,
                views=to_int(m.play_count or m.view_count),
                author=m.user.username if m.user else "",
                caption=(m.caption_text or "").replace("\n", " "),
            )
            for m in medias
            if m.code
        ]
        log.info("tag %s fallback: %d reels", tag, len(reels))
        return reels

    def account_reels(self, query: str, accounts: int = 6, per_account: int = 8) -> list[Reel]:
        authors = self.account_authors(query)
        if not authors:
            return []
        cl = self.connect()
        reels: dict[str, Reel] = {}
        for pk, username in authors[:accounts]:
            try:
                medias, _ = cl.user_medias_paginated_v1(pk, amount=per_account * 2)
            except BLOCKING_ERRORS:
                raise
            except Exception:
                log.warning("medias for %s failed", username, exc_info=True)
                continue
            for m in medias:
                if not m.code:
                    continue
                is_clip = m.product_type == "clips" or (m.media_type == 2 and (m.play_count or m.view_count))
                if not is_clip:
                    continue
                reels.setdefault(m.code, Reel(
                    code=m.code,
                    views=to_int(m.play_count or m.view_count),
                    author=username,
                    caption=(m.caption_text or "").replace("\n", " "),
                ))
            if len(reels) >= accounts * per_account:
                break
        log.info("account_reels %s: %d reels from %d accounts", query, len(reels), min(accounts, len(authors)))
        return list(reels.values())
