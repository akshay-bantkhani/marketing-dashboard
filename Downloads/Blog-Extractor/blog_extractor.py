"""Backwards-compatibility shim — use the blog_extractor package instead.

    pip install -e .
    blog-extract <url>
"""
from blog_extractor.cli import main

if __name__ == "__main__":
    main()
