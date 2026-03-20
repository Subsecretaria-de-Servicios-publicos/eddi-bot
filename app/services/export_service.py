import csv
import io
import json


def export_documents_json(documents: list[dict]) -> str:
    return json.dumps(documents, ensure_ascii=False, indent=2, default=str)


def export_documents_csv(documents: list[dict]) -> str:
    output = io.StringIO()
    fieldnames = [
        "id",
        "source_id",
        "title",
        "url",
        "document_type",
        "organism",
        "topic",
        "status",
        "is_published",
        "content_hash",
        "created_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in documents:
        writer.writerow({k: row.get(k) for k in fieldnames})
    return output.getvalue()