from io import BytesIO
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import httpx
import pdfplumber
from bs4 import BeautifulSoup
from pypdf import PdfReader


PDF_QUERY_KEYS = ("file", "src", "url", "download", "pdf")
DYNAMIC_HTML_EXTENSIONS = {".php", ".asp", ".aspx", ".jsp", ".html", ".htm"}


def _clean_html_text(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)

    return cleaned, title


def _looks_like_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").lower()

    if path.endswith(".pdf"):
        return True

    qs = parse_qs(parsed.query or "")
    for key in PDF_QUERY_KEYS:
        values = qs.get(key) or []
        for value in values:
            value = unquote((value or "").strip())
            if value.lower().endswith(".pdf"):
                return True

    return False


def _extract_pdf_url_from_candidate(base_url: str, raw_value: str | None) -> str | None:
    if not raw_value:
        return None

    raw_value = raw_value.strip()
    if not raw_value:
        return None

    absolute = urljoin(base_url, raw_value)

    if not _looks_like_pdf_url(absolute):
        return None

    parsed = urlparse(absolute)
    qs = parse_qs(parsed.query or "")

    for key in PDF_QUERY_KEYS:
        values = qs.get(key) or []
        for value in values:
            value = unquote((value or "").strip())
            if value.lower().endswith(".pdf"):
                return urljoin(absolute, value)

    return absolute


def _find_embedded_pdf_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")

    for tag_name, attr_name in (
        ("iframe", "src"),
        ("embed", "src"),
        ("object", "data"),
        ("a", "href"),
    ):
        for tag in soup.find_all(tag_name):
            candidate = _extract_pdf_url_from_candidate(base_url, tag.get(attr_name))
            if candidate:
                return candidate

    for tag in soup.find_all(True):
        for attr_name, attr_value in tag.attrs.items():
            values = attr_value if isinstance(attr_value, list) else [attr_value]
            for value in values:
                if not isinstance(value, str):
                    continue
                candidate = _extract_pdf_url_from_candidate(base_url, value)
                if candidate:
                    return candidate

    return None


def _download_pdf_bytes(pdf_url: str, timeout: int = 30) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(pdf_url)
        resp.raise_for_status()

        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
            raise ValueError(f"La URL detectada no devolvió un PDF válido: {pdf_url}")

        return resp.content


def _extract_pdf_title(reader: PdfReader, filename: str | None, source_url: str | None) -> str | None:
    title = None
    try:
        meta = reader.metadata
        if meta:
            raw_title = getattr(meta, "title", None) or meta.get("/Title")
            if raw_title:
                title = str(raw_title).strip()
    except Exception:
        pass

    if not title and filename:
        title = filename.rsplit(".", 1)[0]

    if not title and source_url:
        parsed = urlparse(source_url)
        title = parsed.path.rsplit("/", 1)[-1] or "Documento PDF"

    return title


def extract_text_from_url(url: str, timeout: int = 30) -> dict:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

        final_url = str(resp.url)
        content_type = (resp.headers.get("content-type") or "").lower()

        if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
            extracted = extract_text_from_pdf_bytes(resp.content, source_url=final_url)
            extracted["landing_url"] = url
            return extracted

        html = resp.text
        embedded_pdf_url = _find_embedded_pdf_url(html, final_url)
        if embedded_pdf_url:
            pdf_bytes = _download_pdf_bytes(embedded_pdf_url, timeout=timeout)
            extracted = extract_text_from_pdf_bytes(pdf_bytes, source_url=embedded_pdf_url)
            extracted["landing_url"] = final_url
            extracted["embedded_from_html"] = True
            extracted["embedded_pdf_url"] = embedded_pdf_url
            return extracted

        text, detected_title = _clean_html_text(html)

        return {
            "title": detected_title,
            "content_text": text,
            "source_type": "url",
            "content_type": content_type,
            "url": final_url,
            "landing_url": final_url,
            "metadata": {
                "embedded_from_html": False,
                "embedded_pdf_url": None,
                "pdf_page_count": None,
                "pdf_image_count": None,
                "pdf_has_images": False,
                "low_text_pdf": False,
                "extraction_engine": "html_bs4",
            },
        }


def extract_text_from_pdf_bytes(data: bytes, source_url: str | None = None, filename: str | None = None) -> dict:
    reader = PdfReader(BytesIO(data))
    title = _extract_pdf_title(reader, filename=filename, source_url=source_url)

    page_texts: list[str] = []
    total_chars = 0
    total_images = 0

    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            page_count = len(pdf.pages)

            for idx, page in enumerate(pdf.pages):
                page_text = ""

                # 1) intento con pypdf
                try:
                    page_text = (reader.pages[idx].extract_text() or "").strip()
                except Exception:
                    page_text = ""

                # 2) fallback con pdfplumber
                if not page_text:
                    try:
                        page_text = (page.extract_text() or "").strip()
                    except Exception:
                        page_text = ""

                if page_text:
                    page_texts.append(page_text)
                    total_chars += len(page_text)

                try:
                    total_images += len(page.images or [])
                except Exception:
                    pass

    except Exception:
        # fallback simple si pdfplumber falla
        page_count = len(reader.pages)
        for page in reader.pages:
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception:
                page_text = ""
            if page_text:
                page_texts.append(page_text)
                total_chars += len(page_text)

    text = "\n\n".join(page_texts).strip()

    avg_chars_per_page = (total_chars / page_count) if page_count else 0
    low_text_pdf = total_chars < 800 or avg_chars_per_page < 120
    pdf_has_images = total_images > 0

    return {
        "title": title,
        "content_text": text,
        "source_type": "pdf",
        "content_type": "application/pdf",
        "url": source_url,
        "metadata": {
            "embedded_from_html": False,
            "embedded_pdf_url": source_url,
            "pdf_page_count": page_count,
            "pdf_image_count": total_images,
            "pdf_has_images": pdf_has_images,
            "low_text_pdf": low_text_pdf,
            "extraction_engine": "pypdf+pdfplumber",
        },
    }