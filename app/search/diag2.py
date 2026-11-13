import logging
import sys

from ..config import config
from .instagram import BLOCKING_ERRORS, Instagram, collect_media

QUERIES = ["триммер", "триммер женский", "trimmer", "уход за кожей", "makeup"]
TAGS = ["триммер", "beauty", "косметика", "makeup"]
TABS = (("clips", "clips"), ("top", "default"), ("recent", "default"))


def count(payload):
    found = {}
    collect_media(payload, found)
    return len(found)


def main():
    logging.basicConfig(level=logging.ERROR)
    extra = sys.argv[1:]
    ig = Instagram(config.ig_settings, config.ig_username, config.ig_password, config.ig_sessionid, config.ig_proxy)
    try:
        cl = ig.connect()
        print("вход:", cl.username)
        for q in extra + QUERIES:
            params = {"search_surface": "clips_search_page", "timezone_offset": cl.timezone_offset, "query": q}
            p = cl.private_request("fbsearch/reels_serp/", params=params)
            print(f"reels_serp  «{q}»: рилсов {count(p)}, модулей {len(p.get('reels_serp_modules') or [])}")
        for t in TAGS:
            for tab, rec in TABS:
                data = {
                    "tab": tab, "media_recency_filter": rec, "_uuid": cl.uuid,
                    "include_persistent": "false", "rank_token": cl.rank_token,
                }
                p = cl.private_request(f"tags/{t}/sections/", data=data, with_signature=False)
                print(f"tag #{t} [{tab}]: рилсов {count(p)}, секций {len(p.get('sections') or [])}")
        try:
            ex = cl.private_request("clips/discover/", data={"_uuid": cl.uuid}, with_signature=False)
            print("clips/discover:", count(ex))
        except Exception as e:
            print("clips/discover:", type(e).__name__)
    except BLOCKING_ERRORS as e:
        print("блокировка:", type(e).__name__, e)
    except Exception as e:
        print("ошибка:", type(e).__name__, str(e)[:300])


if __name__ == "__main__":
    main()