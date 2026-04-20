from sqlalchemy import text

from app.db import SessionLocal
from app.services.embedder import embed_document


def main():
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id, chunk_text
                FROM public.document_chunks
                ORDER BY id
            """)
        ).fetchall()

        total = len(rows)
        print(f"Total chunks: {total}")

        updated = 0
        skipped = 0

        for i, row in enumerate(rows, start=1):
            chunk_id = row[0]
            chunk_text = row[1] or ""

            if not chunk_text.strip():
                skipped += 1
                print(f"[{i}/{total}] chunk {chunk_id}: vacío, omitido")
                continue

            vector = embed_document(chunk_text)

            if not vector:
                skipped += 1
                print(f"[{i}/{total}] chunk {chunk_id}: sin embedding")
                continue

            if len(vector) != 3072:
                skipped += 1
                print(f"[{i}/{total}] chunk {chunk_id}: dimensión inesperada {len(vector)}")
                continue

            emb_str = "[" + ",".join(str(x) for x in vector) + "]"

            db.execute(
                text("""
                    UPDATE public.document_chunks
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = :id
                """),
                {"embedding": emb_str, "id": chunk_id},
            )

            updated += 1

            if i % 20 == 0:
                db.commit()
                print(f"[{i}/{total}] commit parcial | actualizados={updated} | omitidos={skipped}")

        db.commit()
        print(f"Reindexado completo OK | actualizados={updated} | omitidos={skipped}")

    finally:
        db.close()


if __name__ == "__main__":
    main()