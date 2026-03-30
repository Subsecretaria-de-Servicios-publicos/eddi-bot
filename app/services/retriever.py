from __future__ import annotations

import re

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
    q = re.sub(r"[¿?¡!,:;()\"'`]", " ", q)
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

    return variants[:5]


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
    params = {"embedding": emb_str, "top_k": max(top_k * 3, 15), **filter_params}
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
    filters_sql, filter_params = _build_common_filters(document_type, organism, topic)

    sql = f"""
        SELECT
            di.id,
            di.document_id,
            di.page_number AS chunk_index,
            di.ocr_text AS chunk_text,
            di.char_count,
            di.score_boost,
            d.title,
            d.url,
            d.document_type,
            d.organism,
            d.topic,
            'image_ocr' AS content_kind,
            di.page_number AS page_number,
            di.image_path AS image_path,
            1 - (di.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_images di
        JOIN documents d ON d.id = di.document_id
        WHERE d.is_published = true
          AND di.embedding IS NOT NULL
          {filters_sql}
        ORDER BY di.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """
    params = {"embedding": emb_str, "top_k": max(top_k * 3, 15), **filter_params}
    return db.execute(text(sql), params).mappings().all()


def _visual_priority_multiplier(question: str, content_kind: str) -> float:
    visual_question = is_visual_ui_question(question)

    if content_kind == "image_ocr":
        return 1.35 if visual_question else 1.05

    if content_kind == "text":
        return 0.92 if visual_question else 1.0

    return 1.0


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
        return []

    emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

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

    merged = list(text_rows) + list(visual_rows)
    rescored = []

    for r in merged:
        sim = float(r["similarity"]) if r["similarity"] is not None else 0.0
        kw = keyword_overlap_score(question, r["chunk_text"] or "")
        boost = float(r["score_boost"]) if r["score_boost"] is not None else 1.0
        kind_multiplier = _visual_priority_multiplier(question, r["content_kind"])

        query_bonus = 1.0
        normalized_semantic = normalize_query_text(semantic_query)
        if normalized_semantic and normalized_semantic in normalize_query_text(r["chunk_text"] or ""):
            query_bonus = 1.08

        final_score = combine_scores(sim, kw, boost) * kind_multiplier * query_bonus

        item = dict(r)
        item["similarity"] = sim
        item["keyword_score"] = kw
        item["kind_multiplier"] = kind_multiplier
        item["query_bonus"] = query_bonus
        item["semantic_query"] = semantic_query
        item["final_score"] = final_score
        item["snippet"] = make_snippet(r["chunk_text"] or "")
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
        filtered = all_results[:top_k]

    if is_visual_ui_question(question):
        visual_first = [x for x in filtered if x.get("content_kind") == "image_ocr"]
        text_next = [x for x in filtered if x.get("content_kind") != "image_ocr"]
        filtered = visual_first + text_next

    return filtered[:top_k]