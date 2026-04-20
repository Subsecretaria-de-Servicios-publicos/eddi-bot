import logging
import re

from google import genai
from google.genai import types

from ..core.config import settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

SYSTEM_PROMPT = """
Sos EDDI, un asistente documental especializado en responder consultas
usando exclusivamente el contexto recuperado desde la base documental.

Reglas:
- Respondé en español claro, profesional, directo y natural.
- Usá solamente la información presente en el contexto recuperado.
- No inventes requisitos, fechas, montos, pasos, botones, ubicaciones ni validaciones.
- Si el contexto es parcial pero útil, respondé con esa evidencia disponible.
- En consultas procedurales o de interfaz, explicá primero brevemente qué hace la funcionalidad y luego desarrollá los pasos.
- Si hay pasos, ordenalos de forma clara y completa.
- Evitá repetir frases introductorias innecesarias.
- No copies texto bruto del documento si puede resumirse mejor.
- Si el contexto menciona botones, opciones o texto visible, conservá esos nombres lo más literal posible.
- No uses markdown.
- No uses encabezados con #.
- No uses listas con *, -, ni numeración markdown.
- Si la evidencia es insuficiente, decilo explícitamente.
"""


def _result(answer: str, fallback_used: bool, model_used: str | None) -> dict:
    return {
        "answer": answer,
        "fallback_used": fallback_used,
        "model_used": model_used,
    }


def _normalize(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _normalize_match_text(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[¿?¡!,:;()\"'`.\-_/\\]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _clean_chunk_text(text: str) -> str:
    value = text or ""

    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)

    value = re.sub(r"\b\d+\s*\n", "\n", value)
    value = re.sub(r"\n\s*\d+\s*\n", "\n", value)
    value = re.sub(r"[ \t]*\|\s*\d+/\d+[ \t]*", " ", value)
    value = re.sub(r"[ \t]*·[ \t]*pág\.?\s*\d+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[ \t]*pág(?:ina)?\.?\s*\d+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[^\S\n]+", " ", value)

    lines = []
    prev_norm = None

    for raw_line in value.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        norm = _normalize(line)
        if norm == prev_norm:
            continue
        prev_norm = norm

        if re.fullmatch(r"[\d\W_]+", line):
            continue

        lines.append(line)

    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\b[a-zA-Z0-9_\-]+\s*\|\s*[a-zA-Z0-9_\- ]+\b", " ", cleaned)
    cleaned = re.sub(r"\b[A-Za-z]\]\b", " ", cleaned)
    cleaned = re.sub(r"[=]{2,}", " ", cleaned)
    cleaned = re.sub(r"[^\S\n]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def _truncate_text(text: str, max_chars: int = 900) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value

    cut = value[:max_chars]
    last_break = max(cut.rfind("\n\n"), cut.rfind("\n"), cut.rfind(". "))
    if last_break >= 220:
        return cut[: last_break + 1].strip()

    return cut.strip() + "..."


def _question_terms(question: str) -> list[str]:
    text = _normalize(question)
    tokens = re.findall(r"[a-záéíóúñ0-9]{3,}", text, flags=re.IGNORECASE)

    stopwords = {
        "como", "cómo", "para", "desde", "hasta", "donde", "dónde", "cual", "cuál",
        "cuando", "cuándo", "sobre", "entre", "tiene", "tengo", "puedo", "puede",
        "debo", "debe", "hacer", "hago", "este", "esta", "estos", "estas", "ese",
        "esa", "esos", "esas", "con", "sin", "por", "del", "las", "los", "una",
        "uno", "unos", "unas", "que", "qué", "porque", "usuario", "sistema",
        "necesito", "quiero", "decime", "decirme", "indicar", "indicarme",
        "pasos", "paso",
    }

    terms = []
    seen = set()

    for token in tokens:
        if token in stopwords:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)

    return terms


def _is_procedural_question(question: str) -> bool:
    q = _normalize(question)
    return any(
        term in q
        for term in [
            "como", "cómo", "paso", "pasos", "anular", "restablecer",
            "modificar", "eliminar", "agregar", "crear", "vincular",
            "guardar", "confirmar", "ingresar", "cargar", "realizar",
        ]
    )


def _is_visual_question(question: str) -> bool:
    q = _normalize(question)
    return any(
        term in q
        for term in [
            "boton", "botón", "pantalla", "icono", "ícono", "campo",
            "texto visible", "label", "etiqueta", "figura", "muestra", "aparece"
        ]
    )


def _extract_focus_phrases(question: str) -> list[str]:
    tokens = _question_terms(question)
    phrases = []
    seen = set()

    for n in range(5, 1, -1):
        for i in range(0, len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n]).strip()
            if len(phrase) < 8:
                continue
            key = _normalize_match_text(phrase)
            if key in seen:
                continue
            seen.add(key)
            phrases.append(phrase)

    return phrases[:12]


def _extract_local_relevant_window(question: str, text: str, max_chars: int = 2200) -> str:
    value = _clean_chunk_text(text or "")
    if not value:
        return ""

    normalized_text = _normalize_match_text(value)
    focus_phrases = _extract_focus_phrases(question)

    if not focus_phrases:
        return _truncate_text(value, max_chars=max_chars)

    best_pos = -1
    for phrase in focus_phrases:
        phrase_norm = _normalize_match_text(phrase)
        pos = normalized_text.find(phrase_norm)
        if pos >= 0 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        return _truncate_text(value, max_chars=max_chars)

    start = max(0, best_pos - 250)
    end = min(len(value), start + max_chars)
    window = value[start:end].strip()

    return _truncate_text(window, max_chars=max_chars)


def _chunk_question_hit_count(question: str, text: str) -> int:
    terms = _question_terms(question)
    normalized_text = _normalize(text)
    hits = 0

    for term in terms:
        if term in normalized_text:
            hits += 1

    return hits


def _best_chunks(retrieved: list[dict], question: str, limit: int = 3) -> list[dict]:
    items = []

    for item in retrieved:
        raw_text = (item.get("merged_text") or item.get("chunk_text") or item.get("content") or "").strip()
        if not raw_text:
            continue

        cleaned = _extract_local_relevant_window(question, raw_text, max_chars=2200)
        if len(cleaned) < 30:
            continue

        score = float(item.get("final_score") or 0.0)
        hit_count = _chunk_question_hit_count(question, cleaned)

        items.append({
            "score": score,
            "hit_count": hit_count,
            "title": item.get("title"),
            "page_number": item.get("page_number"),
            "content_kind": item.get("content_kind") or item.get("chunk_type"),
            "text": cleaned,
            "source_name": item.get("source_name") or item.get("title") or "Sin fuente",
        })

    items.sort(key=lambda x: (x["hit_count"], x["score"]), reverse=True)
    return items[:limit]


def _filter_context_items(question: str, retrieved: list[dict]) -> list[dict]:
    if not retrieved:
        return []

    visual_question = _is_visual_question(question)
    procedural_question = _is_procedural_question(question)

    text_items = [x for x in retrieved if (x.get("content_kind") or x.get("chunk_type")) == "text"]
    visual_items = [x for x in retrieved if (x.get("content_kind") or x.get("chunk_type")) != "text"]

    if not visual_question:
        if procedural_question:
            return text_items[:3] if text_items else []
        return text_items[:4] if text_items else []

    if procedural_question:
        return (visual_items[:2] + text_items[:2])[:4]

    return (visual_items[:3] + text_items[:2])[:5]


def _prefer_exact_section_matches(question: str, retrieved: list[dict]) -> list[dict]:
    if not retrieved:
        return []

    focus_phrases = _extract_focus_phrases(question)
    if not focus_phrases:
        return retrieved

    exact = []
    partial = []
    others = []

    for item in retrieved:
        text_value = item.get("merged_text") or item.get("chunk_text") or item.get("content") or ""
        text_norm = _normalize_match_text(text_value)

        exact_hit = False
        partial_hits = 0

        for phrase in focus_phrases:
            phrase_norm = _normalize_match_text(phrase)
            if phrase_norm in text_norm:
                exact_hit = True
                break

            words = phrase_norm.split()
            if len(words) >= 2:
                hit_count = sum(1 for w in words if w in text_norm)
                if hit_count >= max(2, len(words) - 1):
                    partial_hits += 1

        if exact_hit:
            exact.append(item)
        elif partial_hits > 0:
            partial.append(item)
        else:
            others.append(item)

    if exact:
        return exact + partial + others
    if partial:
        return partial + others
    return retrieved


def _prefer_dominant_title_context(question: str, retrieved: list[dict]) -> list[dict]:
    if not retrieved or len(retrieved) <= 1:
        return retrieved

    q_terms = _question_terms(question)
    q_phrases = _extract_focus_phrases(question)

    title_scores: dict[str, float] = {}

    for item in retrieved:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        title_norm = _normalize(title)
        score = float(item.get("final_score") or 0.0)

        for term in q_terms:
            if term in title_norm:
                score += 1.2

        for phrase in q_phrases[:6]:
            if _normalize_match_text(phrase) in _normalize_match_text(title):
                score += max(2.0, len(phrase.split()) * 0.9)

        title_scores[title] = title_scores.get(title, 0.0) + score

    if not title_scores:
        return retrieved

    ranked = sorted(title_scores.items(), key=lambda x: x[1], reverse=True)
    best_title, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score <= 0:
        return retrieved

    if second_score > 0 and best_score < second_score * 1.20:
        return retrieved

    best_items = []
    others = []

    for item in retrieved:
        if (item.get("title") or "").strip() == best_title:
            best_items.append(item)
        else:
            others.append(item)

    return best_items + others


def _keep_single_title_context(question: str, retrieved: list[dict]) -> list[dict]:
    if not retrieved or len(retrieved) <= 1:
        return retrieved

    if not _is_procedural_question(question):
        return retrieved

    title_scores: dict[str, float] = {}

    for item in retrieved:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        score = float(item.get("final_score") or 0.0)
        title_norm = _normalize(title)

        for term in _question_terms(question):
            if term in title_norm:
                score += 1.5

        for phrase in _extract_focus_phrases(question)[:6]:
            if _normalize_match_text(phrase) in _normalize_match_text(title):
                score += max(2.0, len(phrase.split()))

        title_scores[title] = title_scores.get(title, 0.0) + score

    if not title_scores:
        return retrieved

    ranked = sorted(title_scores.items(), key=lambda x: x[1], reverse=True)
    best_title, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if second_score > 0 and best_score < second_score * 1.35:
        return retrieved

    only_best = [x for x in retrieved if (x.get("title") or "").strip() == best_title]
    return only_best if only_best else retrieved


def _generic_fallback_answer(question: str, retrieved: list[dict]) -> str | None:
    best = _best_chunks(retrieved, question=question, limit=3)
    if not best:
        return None

    procedural = _is_procedural_question(question)

    if procedural:
        combined = "\n\n".join(x["text"] for x in best if x.get("text"))
        combined = _clean_chunk_text(combined)
        combined = _truncate_text(combined, max_chars=2600)

        intro = "Según la documentación recuperada,"
        if best[0].get("title"):
            intro = f"Según la documentación recuperada sobre “{best[0]['title']}”,"

        answer = f"{intro} {combined}"
        return _format_procedural_answer(answer)

    first = best[0]
    first_text = _truncate_text(first["text"], max_chars=1000)

    intro = "Según la documentación recuperada,"
    if first.get("title"):
        intro = f"Según la documentación recuperada sobre “{first['title']}”,"

    return f"{intro} {first_text}"


def _build_context(question: str, retrieved: list[dict]) -> str:
    if not retrieved:
        return "No se recuperó contexto documental."

    blocks = []
    for i, item in enumerate(retrieved, start=1):
        source = item.get("source_name") or item.get("title") or "Sin fuente"
        title = item.get("title") or "Sin título"
        chunk_type = item.get("content_kind") or item.get("chunk_type") or "text"
        raw_content = item.get("merged_text") or item.get("chunk_text") or item.get("content") or ""
        content = _extract_local_relevant_window(question, raw_content, max_chars=1800)
        page = item.get("page_number")

        parts = [
            f"[Fragmento {i}]",
            f"Fuente: {source}",
            f"Título: {title}",
            f"Tipo: {chunk_type}",
        ]
        if page is not None:
            parts.append(f"Página: {page}")
        parts.append("Contenido:")
        parts.append(_truncate_text(content, max_chars=2600))

        blocks.append("\n".join(parts))

    return "\n\n".join(blocks)


def _extract_text(resp) -> str:
    text = getattr(resp, "text", None)
    if text and text.strip():
        return text.strip()

    candidates = getattr(resp, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue

        parts = getattr(content, "parts", None) or []
        texts = []

        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                texts.append(part_text)

        if texts:
            return "\n".join(texts).strip()

    return ""


def _clean_final_answer(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""

    value = re.sub(r"^[#]{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[*\-]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)

    return value.strip()


def _polish_final_answer(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""

    replacements = [
        ("Según la documentación recuperada sobre", "Según la documentación"),
        ("Según la documentación recuperada,", "Según la documentación,"),
        ("Esta funcionalidad será utilizada cuando sea necesario", "Esta funcionalidad se utiliza cuando es necesario"),
        ("A continuación, el sistema nos solicitará que ingresemos:", "Luego, el sistema solicitará:"),
        ("Una vez que presionamos en el botón de", "Al presionar el botón de"),
        ("se deberá ingresar", "hay que ingresar"),
        ("deberemos seleccionar", "hay que seleccionar"),
        ("deberemos ubicarnos", "hay que ubicarse"),
        ("En parte superior derecha", "En la parte superior derecha"),
        ("tal como se ve en la imagen.", "tal como se muestra en la imagen."),
    ]

    for old, new in replacements:
        value = value.replace(old, new)

    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)

    return value.strip()


def _format_procedural_answer(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""

    value = value.replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.split("\n")]

    rebuilt = []
    buffer = ""

    def flush_buffer():
        nonlocal buffer
        if buffer.strip():
            rebuilt.append(buffer.strip())
        buffer = ""

    for line in lines:
        if not line:
            flush_buffer()
            continue

        is_step = re.match(r"^Paso\s+\d+\s*:", line, flags=re.IGNORECASE)
        is_label = re.match(r"^(Importante|Observación|Aclaración)\s*:", line, flags=re.IGNORECASE)

        if is_step or is_label:
            flush_buffer()
            rebuilt.append(line)
            continue

        if re.match(r"^[•●\-\*]\s*", line):
            flush_buffer()
            rebuilt.append(line)
            continue

        if buffer:
            if (
                not buffer.endswith((".", ":", ";"))
                or line[:1].islower()
                or line.startswith(("como ", "en ", "y ", "o ", "para ", "si ", "tal "))
            ):
                buffer = f"{buffer} {line}".strip()
            else:
                flush_buffer()
                buffer = line
        else:
            buffer = line

    flush_buffer()

    value = "\n".join(rebuilt)
    value = re.sub(r"\s*(Paso\s+\d+\s*:)", r"\n\n\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(Importante\s*:)", r"\n\n\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(Observación\s*:)", r"\n\n\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(Aclaración\s*:)", r"\n\n\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\n{3,}", "\n\n", value)

    return value.strip()


def _model_answer_conflicts_with_context(answer: str, question: str, retrieved: list[dict]) -> bool:
    normalized_answer = _normalize(answer)

    negative_patterns = [
        "no contiene información",
        "no hay información",
        "no cuento con información",
        "no puedo ofrecer una respuesta",
        "no se encontró información",
        "la base documental no contiene información",
    ]

    if any(pattern in normalized_answer for pattern in negative_patterns):
        return _generic_fallback_answer(question, retrieved) is not None

    if len(answer.strip()) < 25 and len(retrieved) >= 2:
        return True

    return False


def answer_question(question: str, retrieved: list[dict]) -> dict:
    if not retrieved:
        return _result(
            "No encontré evidencia suficiente en la base documental publicada para responder con precisión esa consulta.",
            fallback_used=True,
            model_used="no_context",
        )

    context_items = _filter_context_items(question, retrieved)
    context_items = _prefer_dominant_title_context(question, context_items)
    context_items = _keep_single_title_context(question, context_items)
    context_items = _prefer_exact_section_matches(question, context_items)

    if not _is_visual_question(question):
        context_items = [x for x in context_items if (x.get("content_kind") or x.get("chunk_type")) == "text"]

    if not context_items:
        return _result(
            "No encontré evidencia suficiente en la base documental publicada para responder con precisión esa consulta.",
            fallback_used=True,
            model_used="no_context_after_filter",
        )

    if not settings.GEMINI_API_KEY or not client:
        logger.error("No hay GEMINI_API_KEY configurada para responder preguntas.")
        fallback = _generic_fallback_answer(question, context_items)
        if fallback:
            return _result(
                fallback,
                fallback_used=True,
                model_used="generic_fallback_missing_gemini_api_key",
            )
        return _result(
            "El sistema no tiene configurado el proveedor de IA para responder en este momento.",
            fallback_used=True,
            model_used="missing_gemini_api_key",
        )

    context_text = _build_context(question, context_items)

    user_prompt = f"""
Pregunta del usuario:
{question}

Contexto documental recuperado:
{context_text}

Instrucciones de respuesta:
- Respondé solo con base en el contexto recuperado.
- Redactá la respuesta como una explicación útil para una persona usuaria del sistema.
- Si la consulta es sobre una funcionalidad, empezá con una frase breve explicando para qué sirve.
- Si hay pasos, presentalos en orden y con redacción limpia.
- No repitas literalmente el título del documento salvo que sea necesario.
- No copies fragmentos cortados ni texto sucio.
- No desarrolles secciones que no respondan a la consulta puntual.
- No uses markdown.
- No inventes nada fuera del contexto.
"""

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
    )

    try:
        resp = client.models.generate_content(
            model=settings.CHAT_MODEL,
            contents=user_prompt,
            config=config,
        )

        answer = _clean_final_answer(_extract_text(resp))
        if _is_procedural_question(question):
            answer = _format_procedural_answer(answer)
        answer = _polish_final_answer(answer)

        if answer:
            if _model_answer_conflicts_with_context(answer, question, context_items):
                fallback = _generic_fallback_answer(question, context_items)
                if fallback:
                    return _result(
                        fallback,
                        fallback_used=True,
                        model_used="generic_fallback_after_conflicting_model_answer",
                    )

            return _result(
                answer,
                fallback_used=False,
                model_used=settings.CHAT_MODEL,
            )

        logger.warning("Gemini respondió sin texto utilizable.")

        fallback = _generic_fallback_answer(question, context_items)
        if fallback:
            return _result(
                fallback,
                fallback_used=True,
                model_used="generic_fallback_empty_model_answer",
            )

        return _result(
            "No encontré una respuesta clara en este momento con el contexto disponible.",
            fallback_used=True,
            model_used="empty_model_answer_no_fallback",
        )

    except Exception as e:
        error_text = str(e)
        error_text_lower = error_text.lower()

        retryable = (
            "503" in error_text
            or "unavailable" in error_text_lower
            or "high demand" in error_text_lower
            or "429" in error_text
            or "resource_exhausted" in error_text_lower
            or "quota" in error_text_lower
        )

        if retryable:
            logger.warning(
                "Gemini saturado al responder. Se usa fallback local. Error: %s",
                error_text,
            )
        else:
            logger.exception("Error respondiendo con Gemini: %s", error_text)

        fallback = _generic_fallback_answer(question, context_items)
        if fallback:
            return _result(
                fallback,
                fallback_used=True,
                model_used="generic_fallback_after_model_exception",
            )

        return _result(
            "En este momento el motor de respuesta está saturado. Probá nuevamente en unos segundos.",
            fallback_used=True,
            model_used="model_unavailable_after_exception",
        )