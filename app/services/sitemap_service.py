import xml.etree.ElementTree as ET

import httpx


def discover_urls_from_sitemap(sitemap_url: str, timeout: int = 30) -> list[str]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(sitemap_url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    urls = []

    for elem in root.iter():
        tag = elem.tag.lower()
        if tag.endswith("loc") and elem.text:
            urls.append(elem.text.strip())

    return urls