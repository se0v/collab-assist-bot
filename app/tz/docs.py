import io
import re
import ssl

import aiohttp
import certifi
from docx import Document

GDOC = re.compile(r"https?://docs\.google\.com/document/d/([\w-]{20,})")
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class DocDownloadError(Exception):
    pass


def docx_to_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    lines = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        is_list = p._p.pPr is not None and p._p.pPr.numPr is not None
        lines.append(f"- {text}" if is_list else text)
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def gdoc_ids(text: str) -> list[str]:
    return list(dict.fromkeys(GDOC.findall(text)))


async def download_gdoc(doc_id: str) -> bytes:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.get(url) as resp:
            data = await resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if resp.status != 200 or "html" in ctype:
                raise DocDownloadError(f"status {resp.status}, {ctype}")
            return data