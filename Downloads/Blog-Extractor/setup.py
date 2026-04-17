from setuptools import setup, find_packages

setup(
    name="blog-extractor",
    version="1.0.0",
    description="Extract Contify blog content into clean DOCX documents",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "python-docx>=1.1.0",
        "lxml>=4.9.0",
        "Pillow>=10.0.0",
        "flask>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "blog-extract=blog_extractor.cli:main",
            "blog-extract-web=blog_extractor.app:main",
        ],
    },
)
