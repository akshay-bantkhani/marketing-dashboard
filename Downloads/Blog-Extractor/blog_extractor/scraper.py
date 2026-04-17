"""Web scraping — fetching pages, locating content, downloading images."""

import io
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .config import CONTENT_SELECTORS, HEADERS
from .cleaner import clean_content as _clean


def fetch_page(url: str) -> str:
    """Fetch HTML content from a URL."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_html(html: str) -> BeautifulSoup:
    """Parse an HTML string into a BeautifulSoup tree."""
    return BeautifulSoup(html, "lxml")


def find_article_content(soup: BeautifulSoup) -> Tag:
    """Locate the main article/content container."""
    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            return el
    return soup.body or soup


def extract_title(soup: BeautifulSoup) -> str:
    """Extract the blog post title (H1 or <title>)."""
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    return "Untitled"


def download_image(img_url: str) -> tuple[bytes, str] | None:
    """Download an image and return ``(bytes, extension)``.

    WebP images are converted to PNG for DOCX compatibility.
    Returns ``None`` on failure or for unsupported formats (SVG).
    """
    try:
        resp = requests.get(img_url, headers=HEADERS, timeout=(5, 10), stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        data = resp.content

        if "png" in content_type:
            ext = "png"
        elif "gif" in content_type:
            ext = "gif"
        elif "webp" in content_type:
            ext = "webp"
        elif "svg" in content_type:
            return None
        else:
            ext = "jpeg"

        # Convert webp → png for DOCX compatibility
        if ext == "webp":
            img = Image.open(io.BytesIO(data))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            ext = "png"

        return data, ext
    except Exception:
        return None


def extract_page_data(url: str, max_chars: int = 50000) -> dict:
    """Single-fetch extraction of title, headings (H1-H5 + bold), and content.

    Returns {"title": str, "headings": [...], "content": str}
    Level 1-5 = H1-H5, Level 6 = standalone <b>/<strong> text.
    """
    html = fetch_page(url)
    soup = parse_html(html)
    title = extract_title(soup)
    container = find_article_content(soup)
    _clean(container)

    headings = []
    seen_texts: set = set()

    for tag in container.find_all(["h1", "h2", "h3", "h4", "h5"]):
        text = tag.get_text(strip=True)
        if text and text not in seen_texts:
            level = int(tag.name[1])
            headings.append({"level": level, "text": text})
            seen_texts.add(text)

    # Standalone bold text as pseudo-headings (level 6)
    for tag in container.find_all(["b", "strong"]):
        parent = tag.parent
        if parent and parent.name in ("p", "li", "div", "td"):
            text = tag.get_text(strip=True)
            if text and 8 <= len(text) <= 150 and text not in seen_texts:
                # Only include if the tag IS the majority of the parent's text
                parent_text = parent.get_text(strip=True)
                if len(text) >= len(parent_text) * 0.6:
                    headings.append({"level": 6, "text": text})
                    seen_texts.add(text)

    text = container.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return {"title": title, "headings": headings, "content": text[:max_chars]}


def extract_headings(url: str) -> dict:
    """Fetch a URL and extract its heading structure (H1-H5 + bold).

    Returns {"title": str, "headings": [{"level": int, "text": str}, ...]}
    """
    data = extract_page_data(url)
    return {"title": data["title"], "headings": data["headings"]}


def extract_content_text(url: str, max_chars: int = 50000) -> str:
    """Fetch a URL and return cleaned article text."""
    data = extract_page_data(url, max_chars=max_chars)
    return data["content"]
