import io
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from .model import TZ

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "tz_base.docx"

REG = "Geologica"
LIGHT = "Geologica Light"
DARK = RGBColor(0x1A, 0x1A, 0x1A)

NUM_DECIMAL = 1
NUM_BULLET = 2

MARKUP = re.compile(r"(\*\*.+?\*\*|==.+?==)")
FONT_ATTRS = ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia")


def _el(tag: str, **attrs) -> OxmlElement:
    el = OxmlElement(tag)
    for key, value in attrs.items():
        el.set(qn(f"w:{key}"), str(value))
    return el


def _fonts_el(name: str) -> OxmlElement:
    el = OxmlElement("w:rFonts")
    for attr in FONT_ATTRS:
        el.set(qn(attr), name)
    return el


def _font(run, name, size=None, bold=False, color=None, highlight=False):
    run.font.name = name
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for attr in FONT_ATTRS:
        rfonts.set(qn(attr), name)
    if size:
        run.font.size = Pt(size)
    if bold:
        run.font.bold = True
    if color is not None:
        run.font.color.rgb = color
    if highlight:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return run


def _rich(par, text, name=LIGHT, size=12, color=DARK, bold=False):
    for chunk in MARKUP.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            _font(par.add_run(chunk[2:-2]), REG, size, bold=True, color=color)
        elif chunk.startswith("==") and chunk.endswith("=="):
            _font(par.add_run(chunk[2:-2]), name, size, bold=bold, color=color, highlight=True)
        else:
            _font(par.add_run(chunk), name, size, bold=bold, color=color)


def _list_item(par, num_id, mark_font=LIGHT, mark_size=24):
    ppr = par._p.get_or_add_pPr()

    numpr = OxmlElement("w:numPr")
    numpr.append(_el("w:ilvl", val=0))
    numpr.append(_el("w:numId", val=num_id))
    ppr.insert(0, numpr)
    ppr.append(_el("w:ind", left=720, hanging=360))

    rpr = OxmlElement("w:rPr")
    rpr.append(_fonts_el(mark_font))
    if mark_size:
        rpr.append(_el("w:sz", val=mark_size))
        rpr.append(_el("w:szCs", val=mark_size))
    ppr.append(rpr)


def _hyperlink(par, url):
    r_id = par.part.relate_to(url, RT.HYPERLINK, is_external=True)

    rpr = OxmlElement("w:rPr")
    rpr.append(_fonts_el(REG))
    rpr.append(_el("w:b", val=1))
    rpr.append(_el("w:color", val="1155cc"))
    rpr.append(_el("w:sz", val=24))
    rpr.append(_el("w:u", val="single"))

    t = OxmlElement("w:t")
    t.text = url
    t.set(qn("xml:space"), "preserve")

    run = OxmlElement("w:r")
    run.append(rpr)
    run.append(t)

    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    link.append(run)
    par._p.append(link)


def _clear_body(doc):
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def render(tz: TZ) -> bytes:
    doc = Document(str(TEMPLATE))
    _clear_body(doc)

    p = doc.add_paragraph()
    _font(p.add_run(tz.title), REG, 18, bold=True)
    p.runs[-1].add_break()
    _rich(p, tz.subtitle, name=REG, size=14, color=None)

    for item in tz.conditions:
        p = doc.add_paragraph()
        _list_item(p, NUM_DECIMAL)
        _rich(p, item)
    if tz.conditions and doc.paragraphs[-1].runs:
        doc.paragraphs[-1].runs[-1].add_break()

    if tz.theses_intro or tz.theses:
        p = doc.add_paragraph()
        _font(p.add_run("Тезисы, которые можно использовать:"), REG, 12, bold=True, color=DARK)
        if tz.theses_intro:
            p.runs[-1].add_break()
            p.runs[-1].add_break()
            _rich(p, tz.theses_intro)
            p.runs[-1].add_break()
        for item in tz.theses:
            p = doc.add_paragraph()
            _list_item(p, NUM_BULLET, mark_font=REG, mark_size=None)
            _rich(p, item, name=REG, size=None, color=None)
        doc.add_paragraph()

    p = doc.add_paragraph()
    _font(p.add_run("Примеры рекламы"), REG, 12, bold=True)
    p = doc.add_paragraph()
    _rich(p, tz.examples_note, color=None)

    if tz.references:
        doc.add_paragraph()
        p = doc.add_paragraph()
        _font(p.add_run("Референсы для роликов:"), REG, 12, bold=True)
        p.runs[-1].add_break()
        for url in tz.references:
            _hyperlink(doc.add_paragraph(), url)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()