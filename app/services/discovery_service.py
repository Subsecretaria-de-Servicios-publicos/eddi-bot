from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


def normalize_url(base_url: str, href: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
        return None
    return urljoin(base_url, href)


def is_same_domain(base_url: str, candidate_url: str) -> bool:
    b = urlparse(base_url)
    c = urlparse(candidate_url)
    return b.netloc == c.netloc


def url_matches_rules(url: str, allowed_prefixes: list[str] | None, allowed_extensions: list[str] | None) -> bool:
    parsed = urlparse(url)
    path = parsed.path or "/"
    last_segment = path.rsplit("/", 1)[-1].lower()

    if allowed_prefixes:
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            return False

    if allowed_extensions:
        normalized_exts = [x.lower().strip(".") for x in allowed_extensions]

        # PDFs u otros archivos explícitos
        for ext in normalized_exts:
            if ext == "html":
                continue
            if last_segment.endswith("." + ext):
                return True

        # HTML / páginas web
        if "html" in normalized_exts:
            # sin extensión -> página web
            if "." not in last_segment:
                return True

            # extensiones de página dinámicas comunes
            dynamic_page_exts = {"html", "htm", "php", "asp", "aspx", "jsp"}
            if any(last_segment.endswith("." + ext) for ext in dynamic_page_exts):
                return True

            return False

    return True


def discover_urls(
    *,
    base_url: str,
    allowed_prefixes: list[str] | None = None,
    allowed_extensions: list[str] | None = None,
    timeout: int = 30,
) -> list[dict]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(base_url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        final_url = normalize_url(base_url, href)
        if not final_url:
            continue
        if not is_same_domain(base_url, final_url):
            continue
        if not url_matches_rules(final_url, allowed_prefixes, allowed_extensions):
            continue
        if final_url in seen:
            continue

        seen.add(final_url)

        title = a.get_text(" ", strip=True) or None
        kind = "pdf" if final_url.lower().endswith(".pdf") else "html"

        items.append({
            "url": final_url,
            "title": title,
            "kind": kind,
        })

    return items