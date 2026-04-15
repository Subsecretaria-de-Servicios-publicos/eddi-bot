import logging
import time

import httpx
from google import genai
from google.genai import types

from ..core.config import settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None


def _extract_embedding(resp) -> list[float]:
    embeddings = getattr(resp, "embeddings", None) or []
    if not embeddings:
        return []

    first = embeddings[0]
    values = getattr(first, "values", None) or []
    return list(values)


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    if not text or not text.strip():
        return []

    if not client or not settings.GEMINI_API_KEY:
        logger.error("No hay GEMINI_API_KEY configurada para embeddings.")
        return []

    last_error = None

    for attempt in range(3):
        try:
            resp = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=[text],
                config=types.EmbedContentConfig(task_type=task_type),
            )
            vector = _extract_embedding(resp)
            if vector:
                return vector

            logger.warning("Gemini embeddings respondió sin vector utilizable.")
            return []

        except (httpx.RemoteProtocolError, httpx.HTTPError) as e:
            last_error = e
            wait_seconds = attempt + 1
            logger.warning(
                "Fallo remoto en Gemini embeddings (intento %s/3). Reintentando en %s s. Error: %s",
                attempt + 1,
                wait_seconds,
                str(e),
            )
            time.sleep(wait_seconds)
            continue

        except Exception as e:
            last_error = e
            logger.exception("Error generando embedding: %s", str(e))
            break

    logger.error("No se pudo generar embedding. Último error: %s", last_error)
    return []


def embed_document(text: str) -> list[float]:
    return embed_text(text, task_type="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    return embed_text(text, task_type="RETRIEVAL_QUERY")