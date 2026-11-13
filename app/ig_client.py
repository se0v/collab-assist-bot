import asyncio

from .config import config
from .search import Instagram

ig_ready = bool(
    config.ig_settings.exists()
    or (config.ig_username and config.ig_password)
    or config.ig_sessionid
)
ig = Instagram(
    config.ig_settings, config.ig_username, config.ig_password,
    config.ig_sessionid, config.ig_proxy,
) if ig_ready else None
ig_lock = asyncio.Lock()
