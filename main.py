import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import config
from app.handlers_search import router as search_router
from app.handlers_tz import router as tz_router


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN is not set")

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(search_router)
    dp.include_router(tz_router)

    await bot.set_my_commands([
        BotCommand(command="help", description="Как оформить сообщение"),
        BotCommand(command="examples", description="База примеров ТЗ"),
        BotCommand(command="search", description="Поиск блогеров"),
        BotCommand(command="id", description="Мой ID"),
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())