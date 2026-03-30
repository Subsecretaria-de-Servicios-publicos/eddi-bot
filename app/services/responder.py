from google import genai

from ..core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

SYSTEM_PROMPT = """
Sos eddi, un asistente documental que responde en español, de forma clara,
natural, conversacional y profesional, usando exclusivamente el contexto recuperado.

Reglas:
- Respondé de manera útil, concreta y humana.
- Usá solamente la información presente en el contexto.
- No inventes requisitos, fechas, montos, pasos ni ubicaciones.
- Si la evidencia es insuficiente, decilo explícitamente.
- Cuando haya evidencia suficiente, respondé como si estuvieras guiando al usuario.
- Si la consulta es procedural, priorizá explicar el paso pedido de forma directa.
- Si el usuario pregunta por un "Paso X", comenzá preferentemente con algo como:
  "Sí. En el Paso X..." o "En el Paso X..."
- Si hay evidencia visual OCR y textual, integrá ambas sin duplicar.
- Si la pregunta es sobre interfaz, pantalla, botones, campos, opciones o texto visible:
  - priorizá la evidencia OCR visual
  - citá el label o texto visible de la forma más literal posible
  - no reemplaces un nombre visible por una paráfrasis abstracta
- No menciones scores internos ni detalles técnicos del retrieval.
- Evitá responder de forma fría o excesivamente burocrática.
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

    prompt = (
        f"{SYSTEM_PROMPT.strip()}\n\n"
        f"{build_user_prompt(question, chunks)}"
    )

    resp = client.models.generate_content(
        model=settings.CHAT_MODEL,
        contents=prompt,
    )

    text_value = getattr(resp, "text", None)
    if text_value:
        return text_value.strip()

    return (
        "No pude generar una respuesta en este momento con el modelo configurado, "
        "aunque sí se recuperó contexto documental."
    )