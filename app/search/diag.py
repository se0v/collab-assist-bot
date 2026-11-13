import json
import logging
import sys
from collections import Counter

from ..config import config
from .instagram import BLOCKING_ERRORS, Instagram, collect_media

WANT = ("code", "pk", "id", "media_type", "product_type", "play_count", "view_count", "ig_play_count", "username")


def paths(node, prefix, counter, samples):
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            counter[path] += 1
            if key in WANT and not isinstance(value, (dict, list)):
                samples.setdefault(path, repr(value)[:40])
            paths(value, path, counter, samples)
    elif isinstance(node, list):
        for value in node:
            paths(value, prefix + "[]", counter, samples)


def show(title, payload):
    print(f"\n===== {title}")
    if not isinstance(payload, (dict, list)):
        print("ответ:", repr(payload)[:300])
        return
    found = {}
    collect_media(payload, found)
    print("рилсов распознано:", len(found), "| с просмотрами:", sum(1 for r in found.values() if r.views))
    counter, samples = Counter(), {}
    paths(payload, "", counter, samples)
    print("верхний уровень:", list(payload)[:15] if isinstance(payload, dict) else "список")
    for path, n in counter.items():
        if path.rsplit(".", 1)[-1] in WANT or path.count(".") + path.count("[]") <= 2:
            print(f"  {path}  x{n}  {samples.get(path, '')}")


def main():
    logging.basicConfig(level=logging.WARNING)
    query = " ".join(sys.argv[1:]) or "триммер женский обзор"
    tag = query.replace(" ", "").lower()
    ig = Instagram(config.ig_settings, config.ig_username, config.ig_password, config.ig_sessionid, config.ig_proxy)
    try:
        cl = ig.connect()
        print("вход выполнен:", cl.username)
        params = {"search_surface": "clips_search_page", "timezone_offset": cl.timezone_offset, "query": query}
        show(f"fbsearch/reels_serp/ «{query}»", cl.private_request("fbsearch/reels_serp/", params=params))
        data = {
            "tab": "clips", "media_recency_filter": "clips", "_uuid": cl.uuid,
            "include_persistent": "false", "rank_token": cl.rank_token,
        }
        show(f"tags/{tag}/sections/", cl.private_request(f"tags/{tag}/sections/", data=data, with_signature=False))
        reels = ig.tag_reels(tag)
        print(f"\ntag_reels({tag}) с запасным методом: {len(reels)}")
    except BLOCKING_ERRORS as e:
        print("Instagram блокирует сессию:", type(e).__name__, e)
    except Exception as e:
        print("ошибка:", type(e).__name__, str(e)[:300])


if __name__ == "__main__":
    main()