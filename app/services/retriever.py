from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.config import settings
from .embedder import embed_text
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
    query_embedding = embed_text(question)

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
        final_score = combine_scores(sim, kw, boost) * kind_multiplier

        item = dict(r)
        item["similarity"] = sim
        item["keyword_score"] = kw
        item["kind_multiplier"] = kind_multiplier
        item["final_score"] = final_score
        item["snippet"] = make_snippet(r["chunk_text"] or "")
        rescored.append(item)

    rescored.sort(key=lambda x: x["final_score"], reverse=True)
    rescored = _dedupe_results(rescored)
    filtered = [x for x in rescored if x["final_score"] >= settings.RAG_MIN_SCORE]

    if is_visual_ui_question(question):
        visual_first = [x for x in filtered if x.get("content_kind") == "image_ocr"]
        text_next = [x for x in filtered if x.get("content_kind") != "image_ocr"]
        filtered = visual_first + text_next

    return filtered[:top_k]