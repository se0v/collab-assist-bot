import asyncio
import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message

from .config import config
from .tz import (
    TZ,
    DocDownloadError,
    ExampleStore,
    Generator,
    NotAProduct,
    apply_defaults,
    docx_to_text,
    download_gdoc,
    gdoc_ids,
    render,
)

log = logging.getLogger(__name__)
router = Router()
generator = Generator(config.llm_base_url, config.llm_api_key, config.llm_model, config.llm_project)
store = ExampleStore(config.examples_dir)

HELP = """Напишите, для какого товара нужно ТЗ, например:
<code>ТЗ по выпрямителю</code>
<code>нужно ТЗ на фен Cosmolex, 3 насадки, ионизация, промокод HAIR10</code>

Чем больше деталей о товаре, тем точнее тезисы. Ссылки на референсы можно добавить в то же сообщение.

База примеров: пришлите готовые ТЗ файлами .docx или ссылками на Google Документы (с доступом по ссылке). Бот будет писать новые ТЗ в их стиле.
/examples - список примеров, /delete 3 - удалить пример №3

Поиск блогеров: /search"""

pending: dict[int, tuple[list[str], asyncio.Task]] = {}


def is_allowed(message: Message) -> bool:
    if not config.allowed_users:
        return True
    return message.from_user is not None and message.from_user.id in config.allowed_users


def make_filename(tz: TZ) -> str:
    parts = ["ТЗ", tz.brand, tz.product, datetime.now().strftime("%d.%m.%Y")]
    clean = [re.sub(r"[^\w\-.]+", "_", p).strip("_") for p in parts if p]
    return "_".join(clean) + ".docx"


async def add_example(data: bytes) -> str | None:
    text = await asyncio.to_thread(docx_to_text, data)
    if len(text) < 50:
        return None
    product = await generator.detect_product(text)
    store.add(product, text)
    return product


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message):
    if is_allowed(message):
        await message.answer(HELP)


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>")


@router.message(Command("examples"))
async def cmd_examples(message: Message):
    if not is_allowed(message):
        return
    items = store.items()
    if not items:
        await message.answer("База примеров пуста. Пришлите ТЗ файлом .docx или ссылкой на Google Документ")
        return
    lines = [f"{i}. <b>{e.product}</b> - {e.text[:60].replace(chr(10), ' ')}..." for i, e in enumerate(items, start=1)]
    await message.answer("Примеры ТЗ:\n" + "\n".join(lines)[:3900])


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject):
    if not is_allowed(message):
        return
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Укажите номер из /examples, например: <code>/delete 3</code>")
        return
    item = store.delete(int(command.args.strip()))
    if item is None:
        await message.answer("Нет примера с таким номером, посмотрите /examples")
    else:
        await message.answer(f"Удалил пример: {item.product}")


@router.message(F.document)
async def on_document(message: Message):
    if not is_allowed(message):
        return
    name = message.document.file_name or ""
    if not name.lower().endswith(".docx"):
        await message.answer("Примеры принимаю только в формате .docx")
        return
    try:
        file = await message.bot.download(message.document)
        product = await add_example(file.read())
    except Exception:
        log.exception("failed to add example %s", name)
        await message.answer(f"Не получилось прочитать {name}")
        return
    if product is None:
        await message.answer(f"В файле {name} почти нет текста, пропускаю")
    else:
        await message.answer(f"Добавил пример: <b>{product}</b> ({name})")


@router.message(F.text | F.caption)
async def on_text(message: Message):
    if not is_allowed(message):
        return
    text = (message.text or message.caption or "").strip()
    if not text or text.startswith("/"):
        return

    uid = message.from_user.id
    if uid in pending:
        parts, task = pending[uid]
        task.cancel()
        parts.append(text)
    else:
        parts = [text]
    pending[uid] = (parts, asyncio.create_task(process_later(message, uid)))


async def import_gdocs(message: Message, ids: list[str]):
    status = await message.answer(f"Загружаю документы: {len(ids)}..")
    added, failed = [], 0
    for doc_id in ids:
        try:
            product = await add_example(await download_gdoc(doc_id))
        except DocDownloadError:
            failed += 1
            continue
        except Exception:
            log.exception("failed to import gdoc %s", doc_id)
            failed += 1
            continue
        if product:
            added.append(product)
        else:
            failed += 1
    lines = [f"Добавлено примеров: {len(added)}"] + [f"- {p}" for p in added]
    if failed:
        lines.append(f"Не удалось открыть: {failed}. Проверьте, что доступ открыт всем, у кого есть ссылка")
    await status.edit_text("\n".join(lines))


async def process_later(message: Message, uid: int):
    try:
        await asyncio.sleep(config.merge_window)
    except asyncio.CancelledError:
        return

    parts, _ = pending.pop(uid, ([], None))
    text = "\n".join(parts)

    ids = gdoc_ids(text)
    if ids:
        await import_gdocs(message, ids)
        return

    status = await message.answer("Пишу ТЗ..")
    try:
        examples = store.pick(text, config.examples_per_request)
        tz = apply_defaults(await generator.generate(text, examples), config.default_brand)
        data = await asyncio.to_thread(render, tz)
        await message.answer_document(BufferedInputFile(data, filename=make_filename(tz)))
        await status.delete()
    except NotAProduct:
        await status.edit_text("Не понял, для какого товара нужно ТЗ. Пример: <code>ТЗ по выпрямителю</code>")
    except Exception:
        log.exception("failed to build tz")
        await status.edit_text("Не получилось собрать ТЗ, попробуйте еще раз")