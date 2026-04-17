"""HTML content cleanup — removes unwanted elements before conversion."""

from bs4 import Tag

from .config import EXCLUDE_SELECTORS


def clean_content(container: Tag) -> None:
    """Remove unwanted elements (ads, nav, sidebar, etc.) from *container* in place."""
    for selector in EXCLUDE_SELECTORS:
        for el in container.select(selector):
            el.decompose()
