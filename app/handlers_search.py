import asyncio
import logging
from datetime import datetime

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from .config import config
from .handlers_tz import is_allowed
from .ig_client import ig, ig_lock
from .search import SearchStopped, build_top_message, build_xlsx, parse_query, run_search

log = logging.getLogger(__name__)
router = Router()

HELP = """Поиск блогеров по нише.

Первая строка - ниша (слова или хештеги через запятую), дальше фильтры по желанию:
<code>/search уход за кожей, #косметика
подписчики 10к-100к
просмотры от 5к
лимит 30</code>

Подписчики и просмотры можно задать так: <code>от 10к</code>, <code>до 1 млн</code>, <code>5000-50000</code>.
Просмотры - медиана по последним 12 рилсам.
Поиск идет медленно, чтобы Instagram не заблокировал аккаунт: обычно 5-10 минут"""

STOP_REASONS = {
    "LoginRequired": "Сессия Instagram временно недоступна. Обратитесь к администратору",
    "ChallengeRequired": "Сессия Instagram временно недоступна. Обратитесь к администратору",
}
SLOW_DOWN = "Необходимо притормозить. Показываю, что успел найти. Повторите поиск через 30-60 минут"


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    if not is_allowed(message):
        return
    if ig is None:
        await message.answer("Поиск не настроен")
        return

    query = parse_query(command.args or "")
    if not query.terms:
        await message.answer(HELP)
        return
    if ig_lock.locked():
        await message.answer("Instagram сейчас занят другим поиском, дождитесь его окончания")
        return

    async with ig_lock:
        status = await message.answer("Запускаю поиск..")

        async def progress(text: str):
            try:
                await status.edit_text(text)
            except TelegramBadRequest:
                pass

        note = ""
        try:
            profiles = await run_search(ig, query, progress, config.search_max_checks)
        except SearchStopped as e:
            profiles = e.found
            note = STOP_REASONS.get(e.reason, SLOW_DOWN)
        except Exception:
            log.exception("search failed")
            await progress("Поиск нестабилен")
            return

        await progress("Поиск завершен")
        await message.answer(build_top_message(profiles, query), disable_web_page_preview=True)
        if profiles:
            name = f"Блогеры_{'_'.join(query.terms)[:40]}_{datetime.now():%d.%m.%Y}.xlsx".replace(" ", "_")
            data = await asyncio.to_thread(build_xlsx, profiles, query)
            await message.answer_document(BufferedInputFile(data, filename=name))
        if note:
            await message.answer(note)
