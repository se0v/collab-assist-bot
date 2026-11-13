import base64
import random
import re
import string

REEL_URL = re.compile(r"https?://(?:www\.)?instagram\.com/(?:[\w.]+/)?(?:reels?|p|tv)/([\w-]{5,})", re.I)
TAIL_NAMES = ("obrf", "psln", "exln", "dlrf", "rpxt", "srtk", "stkn")
TOKEN_CHARS = string.ascii_lowercase + string.digits
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def reel_codes(text: str) -> list[str]:
    return list(dict.fromkeys(REEL_URL.findall(text)))


def clean_url(code: str) -> str:
    return f"https://www.instagram.com/reel/{code}/"


def tail_token(rng: random.Random) -> str:
    body = "".join(rng.choices(TOKEN_CHARS, k=12))
    return base64.b64encode((("1" + body) if rng.random() < 0.6 else body).encode()).decode()


def decorated_url(code: str, rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    return f"{clean_url(code)}?{rng.choice(TAIL_NAMES)}={tail_token(rng)}"


def code_from_pk(pk: str | int) -> str:
    number = int(str(pk).split("_")[0])
    chars = []
    while number:
        number, rest = divmod(number, 64)
        chars.append(ALPHABET[rest])
    return "".join(reversed(chars))
