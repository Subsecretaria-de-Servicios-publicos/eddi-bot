from app.db import SessionLocal
from app.models import DocumentChunk
from app.services.embedder import embed_text


def main():
    db = SessionLocal()
    try:
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.embedding.is_(None))
            .order_by(DocumentChunk.id.asc())
            .all()
        )

        print(f"Chunks sin embedding: {len(chunks)}")

        for i, chunk in enumerate(chunks, start=1):
            emb = embed_text(chunk.chunk_text)
            chunk.embedding = emb

            if i % 10 == 0:
                db.commit()
                print(f"Procesados: {i}")

        db.commit()
        print("Reindexación finalizada.")
    finally:
        db.close()


if __name__ == "__main__":
    main()