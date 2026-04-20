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


def _error_text(exc: Exception) -> str:
    return str(exc or "")


def _is_not_found_embedding_error(exc: Exception) -> bool:
    text = _error_text(exc).lower()
    return (
        "404" in text
        or "not_found" in text
        or "is not found" in text
        or "not supported for embedcontent" in text
    )


def _is_retryable_embedding_error(exc: Exception) -> bool:
    text = _error_text(exc).lower()
    return (
        "429" in text
        or "503" in text
        or "resource_exhausted" in text
        or "unavailable" in text
        or "high demand" in text
        or "timeout" in text
        or "temporarily unavailable" in text
    )


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    if not text or not text.strip():
        return []

    if not client or not settings.GEMINI_API_KEY:
        logger.warning("No hay GEMINI_API_KEY configurada para embeddings. Se usará fallback textual.")
        return []

    last_error = None
    max_retries = 1

    for attempt in range(max_retries):
        try:
            resp = client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=[text],
                config=types.EmbedContentConfig(task_type=task_type),
            )
            vector = _extract_embedding(resp)

            if vector:
                return vector

            logger.warning("Gemini embeddings respondió sin vector utilizable. Se usará fallback textual.")
            return []

        except (httpx.RemoteProtocolError, httpx.HTTPError) as e:
            last_error = e
            wait_seconds = 0.5
            logger.warning(
                "Fallo remoto en Gemini embeddings (intento %s/%s). Reintentando en %s s. Error: %s",
                attempt + 1,
                max_retries,
                wait_seconds,
                str(e),
            )
            time.sleep(wait_seconds)
            continue

        except Exception as e:
            last_error = e

            if _is_not_found_embedding_error(e):
                logger.warning(
                    "El modelo de embeddings configurado no existe o no está soportado (%s). "
                    "Se desactiva embedding y se usará fallback textual.",
                    settings.EMBEDDING_MODEL,
                )
                return []

            if _is_retryable_embedding_error(e):
                wait_seconds = 0.5
                logger.warning(
                    "Gemini embeddings saturado o temporalmente no disponible (intento %s/%s). "
                    "Reintentando en %s s. Error: %s",
                    attempt + 1,
                    max_retries,
                    wait_seconds,
                    str(e),
                )
                time.sleep(wait_seconds)
                continue

            logger.warning(
                "Error generando embedding. Se usará fallback textual. Error: %s",
                str(e),
            )
            return []

    logger.warning("No se pudo generar embedding tras los reintentos. Se usará fallback textual. Último error: %s", last_error)
    return []


def embed_document(text: str, title: str | None = None) -> list[float]:
    return embed_text(text, task_type="RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    return embed_text(text, task_type="RETRIEVAL_QUERY")