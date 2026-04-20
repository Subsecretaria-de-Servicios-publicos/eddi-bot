from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from .embedder import embed_query
from .ranking import keyword_overlap_score, combine_scores


VISUAL_HINT_TERMS = {
    "boton", "botón",
    "pantalla",
    "opcion", "opción",
    "campo",
    "menu", "menú",
    "icono", "ícono",
    "ventana",
    "dice",
    "aparece",
    "figura",
    "muestra",
    "nombre del boton", "nombre del botón",
    "texto del boton", "texto del botón",
    "texto visible",
    "label",
    "etiqueta",
}

NOISE_PATTERNS = [
    r"\bcomo se realiza\b",
    r"\bcómo se realiza\b",
    r"\bcomo hago\b",
    r"\bcómo hago\b",
    r"\bcomo ingresar\b",
    r"\bcómo ingresar\b",
    r"\bcuando ingreso\b",
    r"\bcuándo ingreso\b",
    r"\bquiero saber\b",
    r"\bnecesito saber\b",
    r"\bme podes indicar\b",
    r"\bme podés indicar\b",
    r"\bpodrias decirme\b",
    r"\bpodrías decirme\b",
    r"\bexplicame\b",
    r"\bexplícame\b",
]

ACTION_ALIASES = {
    "anular": {"anular", "anulacion", "anulación", "anulada", "anulado", "anulo", "anula"},
    "restablecer": {"restablecer", "restablecimiento", "restablecida", "restablecido"},
    "modificar": {
        "modificar", "modificacion", "modificación",
        "editar", "edicion", "edición",
        "modifico", "modifica",
    },
    "eliminar": {"eliminar", "eliminacion", "eliminación", "borrar", "elimino", "elimina"},
    "crear": {
        "crear", "creacion", "creación",
        "generar", "genero", "genera",
        "alta", "nuevo", "nueva",
    },
    "agregar": {"agregar", "agregado", "adjuntar", "sumar"},
    "desagregar": {"desagregar", "desagregado"},
    "vincular": {"vincular", "vinculacion", "vinculación", "referencial"},
    "confirmar": {"confirmar", "confirmacion", "confirmación"},
    "cerrar": {"cerrar", "cierre"},
    "derivar": {"derivar", "derivacion", "derivación", "transferir", "transferencia"},
}


def make_snippet(text_value: str, max_len: int = 220) -> str:
    text_value = (text_value or "").strip().replace("\n", " ")
    if len(text_value) <= max_len:
        return text_value
    return text_value[: max_len - 3].rstrip() + "..."


def is_visual_ui_question(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False
    return any(term in q for term in VISUAL_HINT_TERMS)


def normalize_query_text(question: str) -> str:
    q = (question or "").strip().lower()
    q = re.sub(r"[¿?¡!,:;()\"'`.\-_/\\]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def simplify_question(question: str) -> str:
    q = normalize_query_text(question)

    for pattern in NOISE_PATTERNS:
        q = re.sub(pattern, " ", q, flags=re.IGNORECASE)

    q = re.sub(r"\b(el|la|los|las|de|del|al|un|una|y|o|que)\b", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()

    return q


def extract_query_variants(question: str) -> list[str]:
    original = (question or "").strip()
    normalized = normalize_query_text(original)
    simplified = simplify_question(original)

    variants: list[str] = []

    for candidate in [original, normalized, simplified]:
        candidate = (candidate or "").strip()
        if candidate and candidate not in variants:
            variants.append(candidate)

    paso_match = re.search(r"\bpaso\s+(\d+)\b", normalized, flags=re.IGNORECASE)
    if paso_match:
        n = paso_match.group(1)
        for candidate in [f"paso {n}", f"en el paso {n}"]:
            if candidate not in variants:
                variants.append(candidate)

    return variants[:2]


def _query_terms(question: str) -> list[str]:
    normalized = normalize_query_text(question)
    tokens = re.findall(r"[a-záéíóúñ0-9]{3,}", normalized, flags=re.IGNORECASE)

    stopwords = {
        "como", "cómo", "para", "desde", "hasta", "donde", "dónde", "cual", "cuál",
        "cuando", "cuándo", "sobre", "entre", "tiene", "tengo", "puedo", "puede",
        "debo", "debe", "hacer", "hago", "este", "esta", "estos", "estas", "ese",
        "esa", "esos", "esas", "con", "sin", "por", "del", "las", "los", "una",
        "uno", "unos", "unas", "que", "qué", "porque",
        "pasos", "paso",
    }

    out = []
    seen = set()

    for token in tokens:
        if token in stopwords:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)

    return out


def _question_phrases(question: str) -> list[str]:
    terms = _query_terms(question)
    phrases = []
    seen = set()

    for n in range(5, 1, -1):
        for i in range(0, len(terms) - n + 1):
            phrase = " ".join(terms[i:i + n]).strip()
            if len(phrase) < 8:
                continue
            if phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)

    return phrases[:12]


def _phrase_match_bonus(question: str, text_value: str) -> float:
    normalized_text = normalize_query_text(text_value)
    phrases = _question_phrases(question)

    if not phrases:
        return 1.0

    best = 1.0
    for phrase in phrases:
        if phrase in normalized_text:
            word_count = len(phrase.split())
            if word_count >= 4:
                best = max(best, 1.40)
            elif word_count == 3:
                best = max(best, 1.30)
            else:
                best = max(best, 1.18)

    return best


def _extract_action_terms(question: str) -> list[str]:
    terms = _query_terms(question)

    matched = []
    for canonical, aliases in ACTION_ALIASES.items():
        if any(token in aliases for token in terms):
            matched.append(canonical)

    return matched


def _action_match_bonus(question: str, title: str | None, chunk_text: str) -> float:
    actions = _extract_action_terms(question)
    if not actions:
        return 1.0

    title_norm = normalize_query_text(title or "")
    text_norm = normalize_query_text(chunk_text)

    best = 1.0
    for action in actions:
        aliases = ACTION_ALIASES.get(action, {action})

        if any(alias in title_norm for alias in aliases):
            best = max(best, 1.55)
        elif any(alias in text_norm for alias in aliases):
            best = max(best, 1.22)

    return best


def _action_conflict_penalty(question: str, title: str | None, chunk_text: str) -> float:
    actions = _extract_action_terms(question)
    if not actions:
        return 1.0

    title_norm = normalize_query_text(title or "")
    text_norm = normalize_query_text(chunk_text)
    combined = f"{title_norm} {text_norm}"

    asked = set(actions)

    present_other_actions = []
    for canonical, aliases in ACTION_ALIASES.items():
        if canonical in asked:
            continue
        if any(alias in combined for alias in aliases):
            present_other_actions.append(canonical)

    if not present_other_actions:
        return 1.0

    asked_present = False
    for canonical in asked:
        aliases = ACTION_ALIASES.get(canonical, {canonical})
        if any(alias in combined for alias in aliases):
            asked_present = True
            break

    if asked_present:
        return 0.94

    if len(present_other_actions) >= 2:
        return 0.62

    return 0.72


def _is_procedural_question(question: str) -> bool:
    q = normalize_query_text(question)
    procedural_terms = [
        "como", "cómo", "paso", "pasos", "anular", "crear", "modificar",
        "eliminar", "agregar", "vincular", "ingresar", "cargar",
        "guardar", "restablecer", "realizar",
    ]
    return any(term in q for term in procedural_terms)


def _title_match_bonus(question: str, title: str | None) -> float:
    if not title:
        return 1.0

    q_terms = _query_terms(question)
    if not q_terms:
        return 1.0

    title_norm = normalize_query_text(title)
    hits = sum(1 for term in q_terms if term in title_norm)

    if hits >= 3:
        return 1.35
    if hits == 2:
        return 1.22
    if hits == 1:
        return 1.10

    return 1.0


def _distinctive_title_bonus(question: str, title: str | None) -> float:
    if not title:
        return 1.0

    q_terms = _query_terms(question)
    if not q_terms:
        return 1.0

    title_norm = normalize_query_text(title)

    strong_terms = []
    weak_terms = {
        "historial", "actividad", "digital", "eddi",
        "pantalla", "menu", "menú", "paso", "pasos",
    }

    for term in q_terms:
        if term in weak_terms:
            continue
        if len(term) < 4:
            continue
        strong_terms.append(term)

    if not strong_terms:
        return 1.0

    hits = sum(1 for term in strong_terms if term in title_norm)

    if hits >= 2:
        return 1.55
    if hits == 1:
        return 1.25

    return 1.0


def _exact_title_phrase_bonus(question: str, title: str | None) -> float:
    if not title:
        return 1.0

    question_norm = normalize_query_text(question)
    title_norm = normalize_query_text(title)

    if not question_norm or not title_norm:
        return 1.0

    if question_norm == title_norm:
        return 3.00

    if question_norm in title_norm:
        return 2.20

    q_terms = _query_terms(question)
    if not q_terms:
        return 1.0

    joined = " ".join(q_terms).strip()
    if joined and joined in title_norm:
        return 1.90

    hits = sum(1 for term in q_terms if term in title_norm)
    if hits >= max(2, len(q_terms) - 1):
        return 1.60

    return 1.0


def _focus_conflict_penalty(question: str, title: str | None, chunk_text: str) -> float:
    q_terms = set(_query_terms(question))
    combined = f"{normalize_query_text(title or '')} {normalize_query_text(chunk_text)}"

    conflict_groups = [
        {"usuario", "usuarios", "actuacion", "actuación", "actuaciones"},
        {"documento", "documentos", "actuacion", "actuación", "actuaciones"},
        {"organismo", "organismos", "usuario", "usuarios"},
    ]

    penalty = 1.0

    for group in conflict_groups:
        asked = [term for term in group if term in q_terms]
        if not asked:
            continue

        asked_present = any(term in combined for term in asked)
        other_present = any(term in combined for term in group if term not in asked)

        if other_present and not asked_present:
            penalty = min(penalty, 0.45)
        elif other_present and asked_present:
            penalty = min(penalty, 0.82)

    return penalty


def _secondary_action_penalty(question: str, title: str | None, chunk_text: str) -> float:
    actions = _extract_action_terms(question)
    if not actions:
        return 1.0

    title_norm = normalize_query_text(title or "")
    text_norm = normalize_query_text(chunk_text)

    penalty = 1.0

    for action in actions:
        aliases = ACTION_ALIASES.get(action, {action})

        in_title = any(alias in title_norm for alias in aliases)
        in_text = any(alias in text_norm for alias in aliases)

        if in_text and not in_title:
            penalty = min(penalty, 0.72)

    return penalty


def _procedural_content_bonus(question: str, chunk_text: str) -> float:
    if not _is_procedural_question(question):
        return 1.0

    text_norm = normalize_query_text(chunk_text)
    bonus = 1.0

    if "paso 1" in text_norm or "paso 2" in text_norm or "paso 3" in text_norm:
        bonus += 0.18

    if "botón" in chunk_text.lower() or "boton" in text_norm:
        bonus += 0.08

    if "el sistema" in text_norm:
        bonus += 0.05

    if "deberá" in text_norm or "debemos" in text_norm or "se deberá" in text_norm:
        bonus += 0.07

    return min(bonus, 1.30)


def _document_type_penalty(question: str, title: str | None, chunk_text: str) -> float:
    if not _is_procedural_question(question):
        return 1.0

    title_norm = normalize_query_text(title or "")
    text_norm = normalize_query_text(chunk_text)

    glossary_markers = [
        "glosario",
        "definicion",
        "definición",
        "concepto",
        "se entiende por",
        "es cuando",
        "se denomina",
    ]

    hits = 0
    for marker in glossary_markers:
        if marker in title_norm or marker in text_norm:
            hits += 1

    if hits >= 2:
        return 0.68
    if hits == 1:
        return 0.82

    return 1.0


def _build_common_filters(document_type: str | None, organism: str | None, topic: str | None):
    sql = ""
    params = {}
    if document_type:
        sql += " AND d.document_type = :document_type"
        params["document_type"] = document_type
    if organism:
        sql += " AND d.organism = :organism"
        params["organism"] = organism
    if topic:
        sql += " AND d.topic = :topic"
        params["topic"] = topic
    return sql, params


def _retrieve_text_rows(
    db: Session,
    emb_str: str,
    *,
    top_k: int,
    document_type: str | None,
    organism: str | None,
    topic: str | None,
):
    filters_sql, filter_params = _build_common_filters(document_type, organism, topic)

    sql = f"""
        SELECT
            dc.id,
            dc.document_id,
            dc.chunk_index,
            dc.chunk_text,
            dc.char_count,
            dc.score_boost,
            d.title,
            d.url,
            d.document_type,
            d.organism,
            d.topic,
            'text' AS content_kind,
            NULL::integer AS page_number,
            NULL::text AS image_path,
            1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.is_published = true
          AND dc.embedding IS NOT NULL
          {filters_sql}
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """
    params = {"embedding": emb_str, "top_k": max(top_k * 4, 20), **filter_params}
    return db.execute(text(sql), params).mappings().all()


def _retrieve_visual_rows(
    db: Session,
    emb_str: str,
    *,
    top_k: int,
    document_type: str | None,
    organism: str | None,
    topic: str | None,
):
    # Desactivado temporalmente para estabilizar el sistema.
    # document_images puede mantenerse poblada por la ingesta,
    # pero no se usa en retrieval hasta cerrar completamente
    # la migración y validación visual.
    return []


def _retrieve_text_rows_keyword_only(
    db: Session,
    question: str,
    *,
    top_k: int,
    document_type: str | None,
    organism: str | None,
    topic: str | None,
):
    filters_sql, filter_params = _build_common_filters(document_type, organism, topic)

    like_terms = [t for t in _query_terms(question) if len(t) >= 3][:8]
    if not like_terms:
        like_terms = [normalize_query_text(question)[:80]]

    where_parts = []
    params = dict(filter_params)

    score_parts = []
    for i, term in enumerate(like_terms):
        key = f"term_{i}"
        params[key] = f"%{term.lower()}%"

        title_match = f"(CASE WHEN unaccent(LOWER(d.title)) LIKE unaccent(:{key}) THEN 3 ELSE 0 END)"
        chunk_match = f"(CASE WHEN unaccent(LOWER(dc.chunk_text)) LIKE unaccent(:{key}) THEN 1 ELSE 0 END)"

        score_parts.append(title_match)
        score_parts.append(chunk_match)

        where_parts.append(
            f"""(
                unaccent(LOWER(dc.chunk_text)) LIKE unaccent(:{key})
                OR unaccent(LOWER(d.title)) LIKE unaccent(:{key})
            )"""
        )

    where_sql = " OR ".join(where_parts) if where_parts else "TRUE"
    score_sql = " + ".join(score_parts) if score_parts else "0"

    sql = f"""
        SELECT
            dc.id,
            dc.document_id,
            dc.chunk_index,
            dc.chunk_text,
            dc.char_count,
            dc.score_boost,
            d.title,
            d.url,
            d.document_type,
            d.organism,
            d.topic,
            'text' AS content_kind,
            NULL::integer AS page_number,
            NULL::text AS image_path,
            0.0 AS similarity,
            ({score_sql}) AS keyword_db_score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE d.is_published = true
          AND ({where_sql})
          {filters_sql}
        ORDER BY
            ({score_sql}) DESC,
            dc.chunk_index ASC
        LIMIT :top_k
    """
    params["top_k"] = max(top_k * 8, 50)

    return db.execute(text(sql), params).mappings().all()


def _visual_priority_multiplier(question: str, content_kind: str) -> float:
    visual_question = is_visual_ui_question(question)

    if content_kind == "image_ocr":
        return 1.35 if visual_question else 0.55

    if content_kind == "text":
        return 0.92 if visual_question else 1.18

    return 1.0


def _query_term_hits(question: str, text_value: str) -> int:
    question_terms = _query_terms(question)
    text_norm = normalize_query_text(text_value)

    hits = 0
    for token in question_terms:
        if token in text_norm:
            hits += 1

    return hits


def _dedupe_results(items: list[dict]) -> list[dict]:
    seen = set()
    out = []

    for item in items:
        key = (
            item.get("document_id"),
            item.get("content_kind"),
            item.get("page_number"),
            (item.get("chunk_text") or "")[:180],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)

    return out


def _prefer_text_when_not_visual(question: str, items: list[dict]) -> list[dict]:
    if not items:
        return items

    if is_visual_ui_question(question):
        return items

    text_items = [x for x in items if x.get("content_kind") == "text"]
    visual_items = [x for x in items if x.get("content_kind") != "text"]

    if len(text_items) >= 2:
        return text_items + visual_items

    return items


def _merge_neighbor_chunks(items: list[dict]) -> list[dict]:
    if not items:
        return []

    grouped: dict[tuple, list[dict]] = {}
    for item in items:
        key = (item.get("document_id"), item.get("content_kind"))
        grouped.setdefault(key, []).append(item)

    merged_out: list[dict] = []

    for _, rows in grouped.items():
        rows.sort(
            key=lambda x: (
                x.get("page_number") if x.get("page_number") is not None else -1,
                x.get("chunk_index") if x.get("chunk_index") is not None else -1,
                -float(x.get("final_score") or 0.0),
            )
        )

        current = None

        for row in rows:
            if current is None:
                current = dict(row)
                current["merged_text"] = row.get("chunk_text") or ""
                current["merged_parts"] = [row.get("chunk_index")]
                continue

            same_doc = current.get("document_id") == row.get("document_id")
            same_kind = current.get("content_kind") == row.get("content_kind")

            current_idx = current.get("chunk_index")
            row_idx = row.get("chunk_index")
            current_page = current.get("page_number")
            row_page = row.get("page_number")

            contiguous_idx = (
                current_idx is not None
                and row_idx is not None
                and abs(int(row_idx) - int(current_idx)) <= 1
            )

            contiguous_page = (
                current_page is not None
                and row_page is not None
                and abs(int(row_page) - int(current_page)) <= 1
            )

            can_merge = (
                same_doc
                and same_kind
                and (
                    (row.get("content_kind") == "text" and contiguous_idx)
                    or (row.get("content_kind") == "image_ocr" and contiguous_page)
                )
                and len(current.get("merged_parts", [])) < 3
            )

            if can_merge:
                existing = current.get("merged_text") or ""
                extra = row.get("chunk_text") or ""

                if extra and extra not in existing:
                    current["merged_text"] = (existing + "\n\n" + extra).strip()

                current["final_score"] = max(
                    float(current.get("final_score") or 0.0),
                    float(row.get("final_score") or 0.0),
                )
                current["similarity"] = max(
                    float(current.get("similarity") or 0.0),
                    float(row.get("similarity") or 0.0),
                )
                current["keyword_score"] = max(
                    float(current.get("keyword_score") or 0.0),
                    float(row.get("keyword_score") or 0.0),
                )
                current["merged_parts"] = current.get("merged_parts", []) + [row_idx]
                current["char_count"] = len(current.get("merged_text") or "")
                if row_page is not None:
                    current["page_number"] = min(
                        p for p in [current_page, row_page] if p is not None
                    )
                continue

            merged_out.append(current)
            current = dict(row)
            current["merged_text"] = row.get("chunk_text") or ""
            current["merged_parts"] = [row.get("chunk_index")]

        if current is not None:
            merged_out.append(current)

    merged_out.sort(key=lambda x: float(x.get("final_score") or 0.0), reverse=True)
    return merged_out


def _title_relevance_score(question: str, title: str | None) -> float:
    if not title:
        return 0.0

    title_norm = normalize_query_text(title)
    q_terms = _query_terms(question)
    q_phrases = _question_phrases(question)
    actions = _extract_action_terms(question)

    score = 0.0

    for term in q_terms:
        if term in title_norm:
            score += 1.0

    for phrase in q_phrases[:6]:
        if phrase in title_norm:
            score += max(2.0, len(phrase.split()) * 0.8)

    for action in actions:
        aliases = ACTION_ALIASES.get(action, {action})
        if any(alias in title_norm for alias in aliases):
            score += 3.0

    return score


def _prefer_dominant_title(question: str, items: list[dict]) -> list[dict]:
    if not items or len(items) <= 1:
        return items

    title_scores: dict[str, float] = {}

    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        base = float(item.get("final_score") or 0.0)
        title_boost = _title_relevance_score(question, title)
        total = base + title_boost
        title_scores[title] = title_scores.get(title, 0.0) + total

    if not title_scores:
        return items

    ranked_titles = sorted(title_scores.items(), key=lambda x: x[1], reverse=True)
    best_title, best_score = ranked_titles[0]
    second_score = ranked_titles[1][1] if len(ranked_titles) > 1 else 0.0

    if best_score <= 0:
        return items

    strong_lead = best_score >= (second_score * 1.20 if second_score > 0 else 1.0)
    if not strong_lead:
        return items

    best_items = []
    other_items = []

    for item in items:
        if (item.get("title") or "").strip() == best_title:
            best_items.append(item)
        else:
            other_items.append(item)

    return best_items + other_items


def _keep_only_best_title_for_action(question: str, items: list[dict]) -> list[dict]:
    if not items or len(items) <= 1:
        return items

    actions = _extract_action_terms(question)
    if not actions:
        return items

    title_scores: dict[str, float] = {}

    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        score = float(item.get("final_score") or 0.0)
        title_norm = normalize_query_text(title)

        for action in actions:
            aliases = ACTION_ALIASES.get(action, {action})
            if any(alias in title_norm for alias in aliases):
                score += 6.0

        title_scores[title] = title_scores.get(title, 0.0) + score

    if not title_scores:
        return items

    ranked = sorted(title_scores.items(), key=lambda x: x[1], reverse=True)
    best_title, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if second_score > 0 and best_score < second_score * 1.15:
        return items

    filtered = [x for x in items if (x.get("title") or "").strip() == best_title]
    return filtered if filtered else items


def _rescore_keyword_rows(question: str, rows: list[dict], semantic_query: str) -> list[dict]:
    rescored = []

    for r in rows:
        chunk_text = r["chunk_text"] or ""
        kw = max(
            keyword_overlap_score(question, chunk_text),
            float(r.get("keyword_db_score") or 0.0) / 10.0,
        )
        boost = float(r["score_boost"]) if r["score_boost"] is not None else 1.0
        title_bonus = _title_match_bonus(question, r.get("title"))
        exact_title_bonus = _exact_title_phrase_bonus(question, r.get("title"))
        distinctive_bonus = _distinctive_title_bonus(question, r.get("title"))
        procedural_bonus = _procedural_content_bonus(question, chunk_text)
        doc_penalty = _document_type_penalty(question, r.get("title"), chunk_text)
        action_bonus = _action_match_bonus(question, r.get("title"), chunk_text)
        action_penalty = _action_conflict_penalty(question, r.get("title"), chunk_text)
        focus_penalty = _focus_conflict_penalty(question, r.get("title"), chunk_text)
        secondary_action_penalty = _secondary_action_penalty(question, r.get("title"), chunk_text)
        phrase_bonus = _phrase_match_bonus(question, chunk_text)
        term_hits = _query_term_hits(question, chunk_text)
        hit_bonus = 1.0 + min(term_hits * 0.06, 0.30)

        final_score = (
            kw
            * boost
            * title_bonus
            * exact_title_bonus
            * distinctive_bonus
            * procedural_bonus
            * doc_penalty
            * action_bonus
            * action_penalty
            * focus_penalty
            * secondary_action_penalty
            * phrase_bonus
            * hit_bonus
        )

        item = dict(r)
        item["keyword_score"] = kw
        item["term_hits"] = term_hits
        item["title_bonus"] = title_bonus
        item["distinctive_bonus"] = distinctive_bonus
        item["procedural_bonus"] = procedural_bonus
        item["doc_penalty"] = doc_penalty
        item["action_bonus"] = action_bonus
        item["action_penalty"] = action_penalty
        item["focus_penalty"] = focus_penalty
        item["phrase_bonus"] = phrase_bonus
        item["hit_bonus"] = hit_bonus
        item["final_score"] = final_score
        item["snippet"] = make_snippet(chunk_text)
        item["merged_text"] = chunk_text
        item["similarity"] = 0.0
        item["semantic_query"] = semantic_query
        item["exact_title_bonus"] = exact_title_bonus
        item["secondary_action_penalty"] = secondary_action_penalty
        rescored.append(item)

    rescored.sort(key=lambda x: x["final_score"], reverse=True)
    return rescored


def _retrieve_for_single_query(
    db: Session,
    question: str,
    *,
    semantic_query: str,
    top_k: int,
    document_type: str | None,
    organism: str | None,
    topic: str | None,
) -> list[dict]:
    query_embedding = embed_query(semantic_query)

    if not query_embedding:
        keyword_rows = _retrieve_text_rows_keyword_only(
            db,
            question=question,
            top_k=top_k,
            document_type=document_type,
            organism=organism,
            topic=topic,
        )
        return _rescore_keyword_rows(question, keyword_rows, semantic_query)

    if len(query_embedding) != settings.VECTOR_DIMENSION:
        logger.warning(
            "Embedding con dimensión incompatible para búsqueda vectorial. "
            "Esperada=%s, recibida=%s. Se usa fallback textual.",
            settings.VECTOR_DIMENSION,
            len(query_embedding),
        )
        keyword_rows = _retrieve_text_rows_keyword_only(
            db,
            question=question,
            top_k=top_k,
            document_type=document_type,
            organism=organism,
            topic=topic,
        )
        return _rescore_keyword_rows(question, keyword_rows, semantic_query)

    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    try:
        text_rows = _retrieve_text_rows(
            db,
            emb_str,
            top_k=top_k,
            document_type=document_type,
            organism=organism,
            topic=topic,
        )

        visual_rows = _retrieve_visual_rows(
            db,
            emb_str,
            top_k=top_k,
            document_type=document_type,
            organism=organism,
            topic=topic,
        )
    except Exception as e:
        logger.warning("Vector retrieval fallback activado. Error: %r", e)
        db.rollback()
        keyword_rows = _retrieve_text_rows_keyword_only(
            db,
            question=question,
            top_k=top_k,
            document_type=document_type,
            organism=organism,
            topic=topic,
        )
        return _rescore_keyword_rows(question, keyword_rows, semantic_query)

    merged = list(text_rows) + list(visual_rows)
    rescored = []

    for r in merged:
        sim = float(r["similarity"]) if r["similarity"] is not None else 0.0
        chunk_text = r["chunk_text"] or ""
        kw = keyword_overlap_score(question, chunk_text)
        boost = float(r["score_boost"]) if r["score_boost"] is not None else 1.0
        kind_multiplier = _visual_priority_multiplier(question, r["content_kind"])

        query_bonus = 1.0
        normalized_semantic = normalize_query_text(semantic_query)
        normalized_chunk = normalize_query_text(chunk_text)

        if normalized_semantic and normalized_semantic in normalized_chunk:
            query_bonus = 1.08

        term_hits = _query_term_hits(question, chunk_text)
        hit_bonus = 1.0 + min(term_hits * 0.06, 0.30)
        phrase_bonus = _phrase_match_bonus(question, chunk_text)
        title_bonus = _title_match_bonus(question, r.get("title"))
        exact_title_bonus = _exact_title_phrase_bonus(question, r.get("title"))
        distinctive_bonus = _distinctive_title_bonus(question, r.get("title"))
        procedural_bonus = _procedural_content_bonus(question, chunk_text)
        doc_penalty = _document_type_penalty(question, r.get("title"), chunk_text)
        action_bonus = _action_match_bonus(question, r.get("title"), chunk_text)
        action_penalty = _action_conflict_penalty(question, r.get("title"), chunk_text)
        focus_penalty = _focus_conflict_penalty(question, r.get("title"), chunk_text)
        secondary_action_penalty = _secondary_action_penalty(question, r.get("title"), chunk_text)

        final_score = (
            combine_scores(sim, kw, boost)
            * kind_multiplier
            * query_bonus
            * hit_bonus
            * phrase_bonus
            * title_bonus
            * exact_title_bonus
            * distinctive_bonus
            * procedural_bonus
            * doc_penalty
            * action_bonus
            * action_penalty
            * focus_penalty
            * secondary_action_penalty
        )

        item = dict(r)
        item["similarity"] = sim
        item["keyword_score"] = kw
        item["kind_multiplier"] = kind_multiplier
        item["query_bonus"] = query_bonus
        item["hit_bonus"] = hit_bonus
        item["term_hits"] = term_hits
        item["phrase_bonus"] = phrase_bonus
        item["title_bonus"] = title_bonus
        item["distinctive_bonus"] = distinctive_bonus
        item["procedural_bonus"] = procedural_bonus
        item["doc_penalty"] = doc_penalty
        item["action_bonus"] = action_bonus
        item["action_penalty"] = action_penalty
        item["focus_penalty"] = focus_penalty
        item["semantic_query"] = semantic_query
        item["final_score"] = final_score
        item["snippet"] = make_snippet(chunk_text)
        item["merged_text"] = chunk_text
        item["exact_title_bonus"] = exact_title_bonus
        item["secondary_action_penalty"] = secondary_action_penalty
        rescored.append(item)

    rescored.sort(key=lambda x: x["final_score"], reverse=True)
    return rescored


def retrieve_chunks(
    db: Session,
    question: str,
    *,
    top_k: int | None = None,
    document_type: str | None = None,
    organism: str | None = None,
    topic: str | None = None,
) -> list[dict]:
    top_k = top_k or settings.RAG_TOP_K
    visual_question = is_visual_ui_question(question)

    query_variants = extract_query_variants(question)
    all_results: list[dict] = []

    for variant in query_variants:
        all_results.extend(
            _retrieve_for_single_query(
                db,
                question=question,
                semantic_query=variant,
                top_k=top_k,
                document_type=document_type,
                organism=organism,
                topic=topic,
            )
        )

    all_results.sort(key=lambda x: x["final_score"], reverse=True)
    all_results = _dedupe_results(all_results)

    min_score = settings.RAG_MIN_SCORE
    filtered = [x for x in all_results if x["final_score"] >= min_score]

    if not filtered and all_results:
        filtered = all_results[: max(top_k * 2, 6)]

    if not visual_question:
        text_only = [x for x in filtered if x.get("content_kind") == "text"]
        if text_only:
            filtered = text_only

    if visual_question:
        visual_first = [x for x in filtered if x.get("content_kind") == "image_ocr"]
        text_next = [x for x in filtered if x.get("content_kind") != "image_ocr"]
        filtered = visual_first + text_next
    else:
        filtered = _prefer_text_when_not_visual(question, filtered)

    merged_neighbors = _merge_neighbor_chunks(filtered)
    merged_neighbors = _dedupe_results(merged_neighbors)
    merged_neighbors = _prefer_dominant_title(question, merged_neighbors)
    merged_neighbors = _keep_only_best_title_for_action(question, merged_neighbors)

    return merged_neighbors[:top_k]