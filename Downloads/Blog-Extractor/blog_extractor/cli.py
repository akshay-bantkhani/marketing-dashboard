"""Command-line interface for the blog extractor."""

import os
import re
import time
import argparse

from .cleaner import clean_content
from .config import DEFAULT_OUTPUT_DIR
from .converter import DocxBuilder, add_hyperlink, process_element
from .scraper import extract_title, fetch_page, find_article_content, parse_html


def extract_blog(url: str, output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """Extract a blog post from *url* and save as DOCX.

    Returns the path to the saved file.
    """
    print(f"  Fetching: {url}")
    html = fetch_page(url)
    soup = parse_html(html)

    title = extract_title(soup)
    print(f"  Title:    {title}")

    content = find_article_content(soup)
    clean_content(content)

    builder = DocxBuilder(url)
    builder.add_heading(title, level=0)
    builder.doc.add_paragraph("")

    process_element(content, builder)

    # Source URL footer
    builder.doc.add_paragraph("")
    source_para = builder.doc.add_paragraph()
    source_para.add_run("Source: ").bold = True
    add_hyperlink(source_para, url, url)

    # Save
    os.makedirs(output_dir, exist_ok=True)
    safe_title = re.sub(r"[^\w\s-]", "", title)[:80].strip()
    safe_title = re.sub(r"[\s]+", "_", safe_title)
    filename = f"{safe_title}.docx"
    filepath = os.path.join(output_dir, filename)
    builder.save(filepath)
    print(f"  Saved:    {filepath}")
    return filepath


def _load_urls(args) -> list[str]:
    """Collect URLs from CLI positional args and/or a file."""
    urls = list(args.urls) if args.urls else []
    if args.file:
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    return urls


def main():
    parser = argparse.ArgumentParser(
        description="Extract Contify blog content into clean DOCX documents.",
    )
    parser.add_argument("urls", nargs="*", help="Blog URL(s) to extract")
    parser.add_argument("-f", "--file", help="Text file with one URL per line")
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )

    args = parser.parse_args()
    urls = _load_urls(args)

    if not urls:
        parser.error("No URLs provided. Pass URLs as arguments or use -f <file>.")

    print(f"Processing {len(urls)} URL(s)...\n")

    results: list[tuple[str, str | None, str | None]] = []

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}]")
        try:
            filepath = extract_blog(url, args.output)
            results.append((url, filepath, None))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((url, None, str(e)))

        if i < len(urls):
            time.sleep(1)

    # Summary
    succeeded = sum(1 for _, f, _ in results if f)
    print(f"\n{'=' * 60}")
    print(f"Done! {succeeded}/{len(results)} succeeded.\n")
    for url, filepath, error in results:
        if filepath:
            print(f"  OK:   {filepath}")
        else:
            print(f"  FAIL: {url} — {error}")
