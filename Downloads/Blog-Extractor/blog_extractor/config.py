"""Configuration constants for the blog extractor."""

# HTTP request headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Selectors to locate the main article content (tried in order)
CONTENT_SELECTORS = [
    # Contify-specific
    ".pa-post-content",
    ".post-item-inn .borderbox",
    ".post-item-inn",
    # Generic WordPress / blog selectors
    "article .entry-content",
    "article .post-content",
    "article .article-content",
    ".entry-content",
    ".post-content",
    ".article-content",
    ".blog-content",
    ".content-area article",
    "article",
    '[role="main"] .content',
    '[role="main"]',
    "main",
    ".main-content",
    "#content",
    ".content",
]

# Selectors for elements to EXCLUDE from extracted content
EXCLUDE_SELECTORS = [
    "header",
    "footer",
    "nav",
    ".sidebar",
    "#sidebar",
    ".widget",
    ".ad",
    ".ads",
    ".advertisement",
    ".popup",
    ".modal",
    ".newsletter",
    ".subscribe",
    ".signup",
    ".cta-form",
    ".related-posts",
    ".related-articles",
    ".recommended",
    ".share-buttons",
    ".social-share",
    ".author-bio",
    ".comments",
    "#comments",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie-banner",
    ".cookie-consent",
    "script",
    "style",
    "noscript",
    "iframe",
    "form",
    ".wp-block-buttons",
    ".elementor-widget-theme-post-navigation",
    ".post-navigation",
    ".nav-links",
    ".tag-cloud",
    ".wp-block-latest-posts",
    # Contify-specific
    ".table-of-contents",
    "#toc-container",
    ".newsletter-form",
    ".hbspt-form",
    ".post-hero-section .post-meta",
    ".storylane-widget",
    ".share-bar",
    ".post-tags",
]

# Database settings
import os as _os
DATABASE_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data")
DATABASE_PATH = _os.path.join(DATABASE_DIR, "seo_audits.db")
MAX_COMPETITORS = 6
SERP_API_URL = "https://serpapi.com/search"
AHREFS_API_URL = "https://api.ahrefs.com/v3"
SEMRUSH_API_URL = "https://api.semrush.com/"

# DOCX settings
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_FONT_NAME = "Calibri"
DEFAULT_FONT_SIZE_PT = 11
MAX_IMAGE_WIDTH_INCHES = 6.0
IMAGE_DPI = 96
CAPTION_FONT_SIZE_PT = 9
