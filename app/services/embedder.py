from openai import OpenAI

from ..core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_text(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        return []

    resp = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=text,
    )
    return resp.data[0].embedding