import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _ids(value: str) -> frozenset[int]:
    return frozenset(int(x) for x in value.replace(" ", "").split(",") if x)


@dataclass(frozen=True)
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    allowed_users: frozenset[int] = _ids(os.getenv("ALLOWED_USER_IDS", ""))
    default_brand: str = os.getenv("DEFAULT_BRAND", "")
    merge_window: float = float(os.getenv("MERGE_WINDOW_SEC", "1.5"))

    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://llm.api.cloud.yandex.net/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_project: str = os.getenv("LLM_PROJECT", "")
    examples_dir: Path = BASE_DIR / "data" / "examples"
    examples_per_request: int = int(os.getenv("EXAMPLES_PER_REQUEST", "3"))

    ig_username: str = os.getenv("IG_USERNAME", "")
    ig_password: str = os.getenv("IG_PASSWORD", "")
    ig_sessionid: str = os.getenv("IG_SESSIONID", "")
    ig_proxy: str = os.getenv("IG_PROXY", "")
    ig_settings: Path = BASE_DIR / "data" / "ig_session.json"
    search_max_checks: int = int(os.getenv("SEARCH_MAX_CHECKS", "80"))

    ref_search: bool = os.getenv("REF_SEARCH", "1") == "1"
    ref_min_views: int = int(os.getenv("REF_MIN_VIEWS", "5000"))
    ref_count: int = int(os.getenv("REF_COUNT", "6"))
    ref_from_examples: bool = os.getenv("REF_FROM_EXAMPLES", "0") == "1"
    ref_tail: bool = os.getenv("REF_TAIL", "1") == "1"


config = Config()
