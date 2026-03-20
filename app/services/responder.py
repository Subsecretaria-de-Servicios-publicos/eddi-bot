from openai import OpenAI

from ..core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """
Sos EDDI, un asistente documental especializado en responder consultas
usando exclusivamente el contexto recuperado desde la base documental.

Reglas:
- Respondé en español claro, profesional y directo.
- Usá solamente la información presente en el contexto.
- No inventes requisitos, fechas, montos, pasos ni ubicaciones.
- Si la evidencia es insuficiente, decilo explícitamente.
- Cuando haya evidencia suficiente, sintetizá y explicá con claridad.
- Si hay evidencia visual OCR y textual, integrá ambas, sin duplicar.
- Si la pregunta es sobre interfaz, pantalla, botones, campos, opciones o texto visible:
  - priorizá la evidencia OCR visual
  - citá el label o texto visible de la interfaz de la forma más literal posible
  - no reemplaces un nombre visible por una paráfrasis más abstracta
- No menciones scores internos ni detalles técnicos del retrieval.
"""

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
    "label",
    "etiqueta",
    "texto visible",
}


def is_visual_ui_question(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False
    return any(term in q for term in VISUAL_HINT_TERMS)


def build_context(chunks: list[dict]) -> str:
    blocks = []
    for i, ch in enumerate(chunks, start=1):
        content_kind = ch.get("content_kind") or "text"
        kind_label = "OCR visual de página" if content_kind == "image_ocr" else "Texto del documento"

        extra = ""
        if ch.get("page_number") is not None:
            extra += f"Página: {ch.get('page_number')}\n"
        if ch.get("image_path"):
            extra += f"Imagen: {ch.get('image_path')}\n"

        blocks.append(
            f"[FUENTE {i}]\n"
            f"Tipo de evidencia: {kind_label}\n"
            f"Título: {ch.get('title') or 'Documento'}\n"
            f"Tipo: {ch.get('document_type') or ''}\n"
            f"Organismo: {ch.get('organism') or ''}\n"
            f"Tema: {ch.get('topic') or ''}\n"
            f"URL: {ch.get('url') or ''}\n"
            f"{extra}"
            f"Contenido:\n{ch.get('chunk_text') or ''}"
        )
    return "\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    context = build_context(chunks)

    extra_instruction = ""
    if is_visual_ui_question(question):
        extra_instruction = """
Instrucción adicional:
La pregunta es de interfaz visual. Si en el contexto aparece el nombre de un botón,
campo, pestaña, opción o texto de pantalla, respondé con ese texto de manera literal
o lo más literal posible. Priorizá OCR visual de página por encima de texto narrativo.
Si hay conflicto entre una descripción general y un label visible, usá el label visible.
"""

    return (
        f"Contexto documental:\n{context}\n\n"
        f"{extra_instruction}\n"
        f"Pregunta del usuario:\n{question}"
    )


def answer_question(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return (
            "No encontré evidencia suficiente en la base documental publicada "
            "para responder con precisión esa consulta."
        )

    resp = client.chat.completions.create(
        model=settings.CHAT_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, chunks)},
        ],
    )

    return (resp.choices[0].message.content or "").strip()