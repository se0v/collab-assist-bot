import json
import re

from openai import AsyncOpenAI

from .examples import Example
from .model import TZ

URL = re.compile(r"https?://\S+")
JSON_BLOCK = re.compile(r"\{.*\}", re.S)

SYSTEM = """Ты маркетолог бренда и пишешь техническое задание (ТЗ) для блогеров на рекламную интеграцию в Instagram.
Пользователь пишет, для какого товара нужно ТЗ, иногда добавляет бренд и детали.

Верни только JSON без пояснений и без markdown:
{
  "brand": "бренд, если он есть в запросе, иначе пустая строка",
  "product": "название товара в именительном падеже, с большой буквы",
  "theses_intro": "указание блогеру от бренда: легенда подачи и что обязательно проговорить, 2-3 предложения",
  "theses": ["5-7 коротких тезисов, каждый одной строкой, без точки в конце"]
}

Кто кому пишет:
- ТЗ пишет бренд блогеру. Это инструкция, а не текст ролика и не пост.
- theses_intro обращается к блогеру на "вы" и объясняет, как подать товар, как в примерах: "Вы получили рассылку...", "Покажите, как...", "Обязательно проговорите...".
- Никогда не пиши от лица блогера и не обращайся к подписчикам: никаких "Привет, друзья", "Всем привет", "Девочки", "Сегодня расскажу".
- Тезисы - короткие пункты о товаре, которые блогер перескажет своими словами, а не готовые реплики.

Правила:
- Тезисы - о том, что блогер реально покажет или отметит в ролике: результат, ощущения, впечатление, удобство в деле.
- Не пиши про чистку и уход за самим устройством, гарантию, комплектацию, сертификаты и безопасность материалов, если об этом нет в запросе.
- Без канцелярита и рекламных штампов: никаких "идеальное решение", "незаменимый помощник", "легко поддерживать чистоту", "инновационная технология".
- Пиши простыми словами, как люди говорят в сторис.
- Если в запросе есть детали о товаре (особенности, цена, промокод), обязательно используй их.
- Не придумывай конкретные цифры, технологии и характеристики, которых нет в запросе или в примерах.
- Самое важное в 1-2 местах выдели так: ==текст==.
- Если запрос вообще не про товар, верни {"product": ""}."""

STYLE_HINT = """Ниже реальные ТЗ бренда. Пиши новое ТЗ в их стиле: такой же длины, теми же простыми формулировками, с такой же подачей.
Вступление в примерах обычно идет сразу после строки "Тезисы, которые можно использовать", а тезисы - списком после него. Условия сотрудничества и ссылки в примерах не нужны, их бот добавит сам.
Если среди примеров есть ТЗ на такой же товар, опирайся на его тезисы, но не копируй слово в слово.
Детали, относящиеся к другим товарам, не переноси."""

DEFAULT_EXAMPLE = """Товар: Набор для ухода
Вы получили рассылку, как блогер, но уточнили у бренда, что такой же набор блогерский может купить себе любой на сайте. Обязательно проговорить, что уже знакомы с брендом, есть фен.
- Удобный набор, эстетичный вид бокса
- Очень выгодная цена для такого количества продуктов
- У щетки есть насадки для всех зон, особенно удобно, что есть скребок для языка
- После дозатора возвращаться к тюбикам не хочется, удобная упаковка
- Готовый бокс для продуманного и эффективного ухода"""

DETECT = """Тебе прислали техническое задание для блогеров. Определи, для какого товара оно написано.
Верни только JSON: {"product": "название товара в именительном падеже, 1-3 слова"}"""


GREETING = re.compile(
    r"^\s*(всем\s+привет|привет|приветик|здравствуите|здравствуи|добрыи\s+(день|вечер|утро)|хеи|друзья|девочки|ребята|дорогие\s+\w+)"
    r"(\s+(друзья|девочки|ребята|всем|все|мои\s+\w+|дорогие\s+\w+))?"
    r"\s*(,[^.!?\n]*[.!?]*|[.!?]+)\s*",
    re.I,
)


class NotAProduct(Exception):
    pass


def strip_greeting(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        normalized = text.replace("й", "и").replace("Й", "И")
        match = GREETING.match(normalized)
        if match:
            text = text[match.end():]
    return text[:1].upper() + text[1:] if text else text


def clean_thesis(text: str) -> str:
    return strip_greeting(str(text).strip().lstrip("-•* ").rstrip(". "))


def build_prompt(text: str, examples: list[Example]) -> str:
    samples = [f"Товар: {e.product}\n{e.short}" for e in examples] or [DEFAULT_EXAMPLE]
    blocks = "\n\n".join(f"=== Пример {i} ===\n{s}" for i, s in enumerate(samples, start=1))
    return f"{STYLE_HINT}\n\n{blocks}\n\n=== Запрос ===\n{text}"


class Generator:
    def __init__(self, base_url: str, api_key: str, model: str, project: str = ""):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, project=project or None)
        self.model = model

    async def _ask(self, system: str, text: str, max_tokens: int = 1500) -> dict:
        resp = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.4,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        )
        content = resp.choices[0].message.content or ""
        match = JSON_BLOCK.search(content)
        if not match:
            raise ValueError(f"no json in answer: {content[:200]}")
        return json.loads(match.group(0))

    async def _ask_twice(self, system: str, text: str, max_tokens: int = 1500) -> dict:
        try:
            return await self._ask(system, text, max_tokens)
        except (ValueError, json.JSONDecodeError):
            return await self._ask(system, text, max_tokens)

    async def detect_product(self, text: str) -> str:
        try:
            data = await self._ask_twice(DETECT, text[:4000], max_tokens=100)
        except (ValueError, json.JSONDecodeError):
            return "Без названия"
        return str(data.get("product") or "").strip() or "Без названия"

    async def generate(self, text: str, examples: list[Example] | None = None) -> TZ:
        data = await self._ask_twice(SYSTEM, build_prompt(text, examples or []))

        product = str(data.get("product") or "").strip()
        theses = [clean_thesis(t) for t in data.get("theses") or []]
        theses = [t for t in theses if t]
        if not product or not theses:
            raise NotAProduct()

        return TZ(
            brand=str(data.get("brand") or "").strip(),
            product=product,
            theses_intro=strip_greeting(str(data.get("theses_intro") or "").strip()),
            theses=theses,
            references=URL.findall(text),
        )