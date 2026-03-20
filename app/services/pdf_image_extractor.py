from __future__ import annotations

import re
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
VISUAL_DIR = STATIC_DIR / "generated" / "doc_pages"


def _clean_ocr_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_for_match(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def delete_visual_assets_for_document(doc_id: int) -> None:
    doc_dir = VISUAL_DIR / f"doc_{doc_id}"
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)


def _extract_ocr_blocks(img) -> tuple[str, list[dict]]:
    if pytesseract is None:
        return "", []

    try:
        data = pytesseract.image_to_data(
            img,
            lang="spa",
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )
    except Exception:
        return "", []

    blocks = []
    full_parts = []

    n = len(data.get("text", []))
    for i in range(n):
        raw_text = (data["text"][i] or "").strip()
        if not raw_text:
            continue

        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1

        if conf < 0:
            continue

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        clean = _clean_ocr_text(raw_text)
        if not clean:
            continue

        full_parts.append(clean)

        blocks.append({
            "text": clean,
            "conf": conf,
            "x1": left,
            "y1": top,
            "x2": left + width,
            "y2": top + height,
            "w": width,
            "h": height,
        })

    return _clean_ocr_text(" ".join(full_parts)), blocks


def extract_visual_pages_from_pdf_bytes(
    *,
    data: bytes,
    doc_id: int,
    ocr_lang: str = "spa",
    zoom: float = 2.0,
) -> list[dict]:
    if fitz is None:
        raise RuntimeError("PyMuPDF no está instalado")
    if Image is None:
        raise RuntimeError("Pillow no está instalado")

    delete_visual_assets_for_document(doc_id)
    out_dir = VISUAL_DIR / f"doc_{doc_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf = fitz.open(stream=data, filetype="pdf")
    items: list[dict] = []

    for idx, page in enumerate(pdf, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png_bytes = pix.tobytes("png")

        filename = f"page_{idx:04d}.png"
        disk_path = out_dir / filename
        web_path = f"/static/generated/doc_pages/doc_{doc_id}/{filename}"

        disk_path.write_bytes(png_bytes)

        ocr_text = ""
        ocr_blocks = []
        ocr_error = None

        if pytesseract is not None:
            try:
                img = Image.open(BytesIO(png_bytes))
                ocr_text, ocr_blocks = _extract_ocr_blocks(img)
            except Exception as e:
                ocr_error = str(e)

        items.append({
            "page_number": idx,
            "image_index": 1,
            "image_path": web_path,
            "ocr_text": ocr_text or None,
            "caption": f"Página {idx} - OCR visual",
            "char_count": len(ocr_text or ""),
            "metadata_json": {
                "page_number": idx,
                "width": pix.width,
                "height": pix.height,
                "ocr_lang": ocr_lang,
                "ocr_error": ocr_error,
                "ocr_blocks_json": ocr_blocks,
                "created_at": datetime.utcnow().isoformat(),
            },
        })

    pdf.close()
    return items