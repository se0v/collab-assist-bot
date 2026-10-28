import io
from html import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .instagram import Profile
from .query import SearchQuery, human

COLUMNS = [
    ("Ник", 22),
    ("Ссылка", 38),
    ("Имя", 24),
    ("Подписчики", 13),
    ("Медиана просмотров", 18),
    ("Средние просмотры", 17),
    ("ER, %", 9),
    ("Рилсов проверено", 16),
    ("Последний рилс", 15),
    ("Категория", 20),
    ("Email", 26),
    ("Где найден", 24),
    ("Описание", 60),
]


def build_xlsx(profiles: list[Profile], query: SearchQuery) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Блогеры"

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1A1A1A")
    for col, (title, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = width

    for row, p in enumerate(profiles, start=2):
        values = [
            "@" + p.username,
            p.url,
            p.full_name,
            p.followers,
            p.median_views,
            p.avg_views,
            p.er,
            p.reels_count,
            p.last_post.date() if p.last_post else None,
            p.category,
            p.email,
            p.source_tag,
            p.bio,
        ]
        for col, value in enumerate(values, start=1):
            ws.cell(row=row, column=col, value=value)
        link = ws.cell(row=row, column=2)
        link.hyperlink = p.url
        link.font = Font(color="1155CC", underline="single")
        for col in (4, 5, 6):
            ws.cell(row=row, column=col).number_format = "# ##0"
        ws.cell(row=row, column=9).number_format = "DD.MM.YYYY"

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(profiles) + 1, 2)}"

    info = wb.create_sheet("Запрос")
    rows = [
        ("Ниша", ", ".join(query.terms)),
        ("Подписчики", str(query.followers)),
        ("Медиана просмотров", str(query.views)),
        ("Найдено", len(profiles)),
    ]
    for r, (k, v) in enumerate(rows, start=1):
        info.cell(row=r, column=1, value=k).font = Font(bold=True)
        info.cell(row=r, column=2, value=v)
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 50

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_top_message(profiles: list[Profile], query: SearchQuery, top: int = 10) -> str:
    head = (
        f"<b>Ниша:</b> {escape(', '.join(query.terms))}\n"
        f"<b>Подписчики:</b> {query.followers}, <b>просмотры:</b> {query.views}\n"
        f"<b>Найдено:</b> {len(profiles)}\n"
    )
    if not profiles:
        return head + "\nНикого не нашел. Попробуйте другие слова или мягче фильтры"
    lines = []
    for i, p in enumerate(profiles[:top], start=1):
        lines.append(
            f'{i}. <a href="{p.url}">@{escape(p.username)}</a> - '
            f"{human(p.followers)} подп., ~{human(p.median_views)} просм., ER {p.er}%"
        )
    return head + "\n" + "\n".join(lines)