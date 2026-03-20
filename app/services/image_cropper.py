from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except Exception:
    Image = None


def _normalize(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def _tokenize(text: str) -> list[str]:
    return [t for t in _normalize(text).replace("?", " ").replace(",", " ").replace(".", " ").split() if len(t) >= 3]


def pick_best_ocr_block(blocks: list[dict], question: str) -> dict | None:
    if not blocks:
        return None

    tokens = _tokenize(question)
    if not tokens:
        return None

    ranked = []
    for block in blocks:
        text_value = _normalize(block.get("text") or "")
        score = 0

        for tk in tokens:
            if tk in text_value:
                score += 3

        if "firmar" in text_value:
            score += 4
        if "contrasena" in text_value or "contraseña" in text_value:
            score += 4
        if "certificado" in text_value:
            score += 4
        if "seleccionar" in text_value:
            score += 2
        if "boton" in text_value or "botón" in text_value:
            score += 1

        ranked.append((score, block))

    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best_block = ranked[0]
    if best_score <= 0:
        return None
    return best_block


def generate_crop_for_block(
    *,
    image_abspath: str,
    crop_abspath: str,
    block: dict,
    margin: int = 36,
) -> bool:
    if Image is None:
        return False

    img_path = Path(image_abspath)
    out_path = Path(crop_abspath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not img_path.exists():
        return False

    with Image.open(img_path) as img:
        width, height = img.size

        x1 = max(0, int(block["x1"]) - margin)
        y1 = max(0, int(block["y1"]) - margin)
        x2 = min(width, int(block["x2"]) + margin)
        y2 = min(height, int(block["y2"]) + margin)

        if x2 <= x1 or y2 <= y1:
            return False

        crop = img.crop((x1, y1, x2, y2))
        crop.save(out_path, format="PNG")

    return True