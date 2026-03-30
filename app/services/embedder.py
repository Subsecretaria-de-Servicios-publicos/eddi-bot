from google import genai
from google.genai import types

from ..core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)


def _extract_values(resp) -> list[float] | None:
    embeddings = getattr(resp, "embeddings", None)
    if not embeddings:
        return None

    first = embeddings[0]
    values = getattr(first, "values", None)
    if not values:
        return None

    return [float(x) for x in values]


def embed_text(
    text: str,
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
    title: str | None = None,
) -> list[float] | None:
    value = (text or "").strip()
    if not value:
        return None

    config = types.EmbedContentConfig(
        output_dimensionality=1536,
        task_type=task_type,
        title=title if task_type == "RETRIEVAL_DOCUMENT" else None,
    )

    resp = client.models.embed_content(
        model=settings.EMBEDDING_MODEL,
        contents=value,
        config=config,
    )

    return _extract_values(resp)


def embed_document(text: str, title: str | None = None) -> list[float] | None:
    return embed_text(
        text,
        task_type="RETRIEVAL_DOCUMENT",
        title=title,
    )


def embed_query(text: str) -> list[float] | None:
    return embed_text(
        text,
        task_type="QUESTION_ANSWERING",
    )