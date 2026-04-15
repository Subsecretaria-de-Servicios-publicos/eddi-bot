from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ChatRequest, ChatResponse, ChatSourceItem
from ..models import ChatSession, ChatMessage, DocumentImage
from ..services.retriever import retrieve_chunks
from ..services.responder import answer_question
from ..services.image_cropper import pick_best_ocr_block, generate_crop_for_block

router = APIRouter(prefix="/rag/eddi", tags=["public-chat"])


def build_crop_for_source(db: Session, source_item: dict, question: str) -> str | None:
    if source_item.get("content_kind") != "image_ocr":
        return None
    if not source_item.get("image_path"):
        return None

    doc_id = source_item.get("document_id")
    page_number = source_item.get("page_number")
    if not doc_id or not page_number:
        return None

    row = (
        db.query(DocumentImage)
        .filter(
            DocumentImage.document_id == doc_id,
            DocumentImage.page_number == page_number,
        )
        .first()
    )
    if not row:
        return None

    meta = row.metadata_json or {}
    blocks = meta.get("ocr_blocks_json") or []
    best_block = pick_best_ocr_block(blocks, question)
    if not best_block:
        return None

    root_dir = Path(__file__).resolve().parents[1]
    image_rel = row.image_path.lstrip("/")
    image_abs = root_dir / image_rel

    crop_rel = f"static/generated/doc_pages/doc_{doc_id}/crops/page_{int(page_number):04d}.png"
    crop_abs = root_dir / crop_rel

    ok = generate_crop_for_block(
        image_abspath=str(image_abs),
        crop_abspath=str(crop_abs),
        block=best_block,
        margin=42,
    )
    if not ok:
        return None

    return "/" + crop_rel.replace("\\", "/")


def _normalize_answer_result(result) -> tuple[str, bool, str | None]:
    if isinstance(result, dict):
        answer = str(result.get("answer") or "").strip()
        fallback_used = bool(result.get("fallback_used", False))
        model_used = result.get("model_used")
        return answer, fallback_used, model_used

    answer = str(result or "").strip()
    return answer, False, None


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    session_key = payload.session_key or str(uuid4())

    session = db.query(ChatSession).filter(ChatSession.session_key == session_key).first()
    if not session:
        session = ChatSession(
            session_key=session_key,
            channel=payload.channel or "web",
        )
        db.add(session)
        db.flush()

    try:
        retrieved = retrieve_chunks(
            db,
            payload.message,
            document_type=payload.document_type,
            organism=payload.organism,
            topic=payload.topic,
        )
        print("DEBUG chat question:", payload.message)
        print("DEBUG retrieved count:", len(retrieved))
        for i, r in enumerate(retrieved[:5], start=1):
            print(
                "DEBUG chunk",
                i,
                {
                    "title": r.get("title"),
                    "content_kind": r.get("content_kind"),
                    "final_score": r.get("final_score"),
                    "document_id": r.get("document_id"),
                }
            )
    except Exception as e:
        print("DEBUG retrieve_chunks error:", repr(e))
        db.rollback()

        session = db.query(ChatSession).filter(ChatSession.session_key == session_key).first()
        if not session:
            session = ChatSession(
                session_key=session_key,
                channel=payload.channel or "web",
            )
            db.add(session)
            db.flush()

        retrieved = []

    fallback_used = False
    model_used = None

    try:
        result = answer_question(payload.message, retrieved)
        answer, fallback_used, model_used = _normalize_answer_result(result)

        if not answer:
            answer = "No encontré una respuesta clara en este momento con el contexto disponible."
            fallback_used = True
            if not model_used:
                model_used = "empty_answer_fallback"

    except Exception as e:
        print("DEBUG answer_question error:", repr(e))
        answer = "Ocurrió un error al generar la respuesta en este momento."
        fallback_used = True
        model_used = "router_exception_fallback"

    user_retrieval_json = {
        "filters": {
            "document_type": payload.document_type,
            "organism": payload.organism,
            "topic": payload.topic,
        },
        "message": payload.message,
        "session_key": session_key,
    }

    assistant_retrieval_json = {
        "chunks": retrieved,
        "used_chunks": len(retrieved),
        "meta": {
            "fallback_used": fallback_used,
            "model_used": model_used,
            "retrieved_count": len(retrieved),
        },
    }

    try:
        db.add(ChatMessage(
            session_id=session.id,
            role="user",
            message_text=payload.message,
            retrieval_json=user_retrieval_json,
        ))

        db.add(ChatMessage(
            session_id=session.id,
            role="assistant",
            message_text=answer,
            retrieval_json=assistant_retrieval_json,
        ))

        db.commit()

    except Exception:
        db.rollback()
        raise

    sources = []
    seen = set()

    for r in retrieved:
        key = (
            r.get("document_id"),
            r.get("content_kind"),
            r.get("page_number"),
            r.get("image_path"),
        )
        if key in seen:
            continue
        seen.add(key)

        crop_path = build_crop_for_source(db, r, payload.message)

        sources.append(ChatSourceItem(
            document_id=r.get("document_id"),
            title=r.get("title"),
            url=r.get("url"),
            document_type=r.get("document_type"),
            similarity=float(r["final_score"]) if r.get("final_score") is not None else None,
            snippet=r.get("snippet"),
            content_kind=r.get("content_kind"),
            page_number=r.get("page_number"),
            image_path=r.get("image_path"),
            crop_path=crop_path,
        ))

    if len(retrieved) >= 4:
        confidence = "high"
    elif len(retrieved) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return ChatResponse(
        answer=answer,
        session_key=session_key,
        sources=sources,
        used_chunks=len(retrieved),
        confidence=confidence,
    )