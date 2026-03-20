from ..core.config import settings


def chunk_text(text: str, heading: str | None = None) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []

    size = settings.RAG_CHUNK_SIZE
    overlap = settings.RAG_CHUNK_OVERLAP

    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()

        if piece:
            chunks.append({
                "chunk_index": idx,
                "heading": heading,
                "chunk_text": piece,
                "char_count": len(piece),
            })
            idx += 1

        if end == len(text):
            break

        start = end - overlap

    return chunks