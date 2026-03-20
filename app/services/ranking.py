import re


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    parts = re.findall(r"[a-záéíóúñ0-9]+", text, flags=re.IGNORECASE)
    return [p for p in parts if len(p) >= 3]


def keyword_overlap_score(query: str, chunk_text: str) -> float:
    q_tokens = set(tokenize(query))
    c_tokens = set(tokenize(chunk_text))

    if not q_tokens or not c_tokens:
        return 0.0

    overlap = q_tokens.intersection(c_tokens)
    return len(overlap) / max(len(q_tokens), 1)


def combine_scores(vector_similarity: float, keyword_score: float, boost: float = 1.0) -> float:
    return (vector_similarity * 0.75 + keyword_score * 0.25) * boost