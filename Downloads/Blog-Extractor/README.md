# Blog Extractor + SEO Content Audit Tool

A Flask web app with three tools:
1. **Extract to DOCX** — Extract any blog URL into a clean Word document
2. **Check Outdated Info** — AI-powered content audit using Groq (Llama 70B) to find stale stats, pricing, and facts
3. **SEO Content Audit** — Full competitor analysis: keyword research, heading gap analysis, AI recommendations, content plan

---

## Quick Start

### 1. Install Python 3.10+
Download from [python.org](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install.

### 2. Clone / download this repo
```bash
git clone https://github.com/YOUR_USERNAME/Blog-Extractor.git
cd Blog-Extractor
```

### 3. Install dependencies
```bash
pip install -e .
```

### 4. Start the server
```bash
python start_server.py
```

### 5. Open in browser
Go to **http://127.0.0.1:5000**

---

## Features

### Tab 1: Extract to DOCX
- Paste one or multiple blog URLs (one per line)
- Extracts title, headings, paragraphs, lists, tables, bold, italic, links
- Optional: include images (downloaded and embedded)
- Bulk download as `.zip`

### Tab 2: Check Outdated Info
- Paste blog URLs → AI reads the full content
- Flags: outdated stats, old pricing, stale G2/Capterra ratings, expired forecasts, dead companies, old tool features
- Severity levels: High / Medium / Low
- Powered by **Groq API** (free) — get key at [console.groq.com/keys](https://console.groq.com/keys)

### Tab 3: SEO Content Audit (5-step wizard)

**Step 1 — Input & Keyword Research**
- Analyze any blog URL → extracts current heading structure (H1–H5 + bold)
- **Auto Keyword Research**: enter keyword → fetches related keywords from Ahrefs + SEMrush APIs, searches Google for AI overviews, PAA questions, related searches
- Auto-fills keyword data and PAA fields
- Content verification: AI checks your blog for outdated info

**Step 2 — Competitor Analysis**
- Paste competitor URLs (up to 6) or auto-discover via SERP
- **SERP Research**: search any keyword → see Google results (with SerpAPI) or DuckDuckGo (free)
- Heading comparison grid: your blog vs all competitors side-by-side (H1–H5 + B)
- "Show Article Content" toggle per competitor
- AI Overview: Groq synthesizes what all top-ranking pages cover
- Topic Gap Analysis matrix: what competitors cover that you don't

**Step 3 — AI Recommendations**
- 3-specialist AI panel (Content + PMM + SEO) analyzes everything and recommends a heading structure
- Shows diff: what to add, change, or remove
- Gap headings highlighted in orange

**Step 4 — Edit Framework**
- Editable list: adjust heading levels, text, accept/reject AI suggestions
- Add custom headings, reset to AI recommendations
- Content guidelines system for brand voice / style rules

**Step 5 — Final Plan**
- Generate final content plan with change rationale
- Export as DOCX

---

## API Keys Required

| Feature | Key | Where to get |
|---------|-----|--------------|
| Outdated info check | **Groq API** (free) | [console.groq.com/keys](https://console.groq.com/keys) |
| AI recommendations | **Groq API** (free) | same |
| Keyword research | **Ahrefs API** | [ahrefs.com/api](https://ahrefs.com/api) |
| Keyword research | **SEMrush API** | [semrush.com/api](https://www.semrush.com/api-analytics/) |
| Google SERP data | **SerpAPI** (optional) | [serpapi.com](https://serpapi.com) |

All keys are saved in your browser's localStorage — never sent to any server except their own APIs.

---

## Project Structure

```
Blog-Extractor/
├── blog_extractor/
│   ├── app.py          # Flask web UI + all routes
│   ├── scraper.py      # URL fetching, heading/content extraction (H1-H5 + bold)
│   ├── cleaner.py      # HTML cleanup (removes nav, ads, sidebar, etc.)
│   ├── converter.py    # HTML → DOCX conversion
│   ├── analyzer.py     # Groq AI: outdated content detection
│   ├── seo_audit.py    # SEO audit: gap analysis, Ahrefs/SEMrush/SERP, AI recommendations
│   ├── database.py     # SQLite: audits, keywords, competitors, headings, recommendations
│   ├── config.py       # Constants: selectors, API URLs, settings
│   └── cli.py          # Command-line interface
├── start_server.py     # Quick-start (auto-installs deps)
├── setup.py
└── output/             # Generated DOCX files (gitignored)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not found | Install Python from python.org, check "Add to PATH" |
| Port 5000 in use | Close other terminal or restart |
| Groq API error | Check key at console.groq.com, or the model may be rate-limited — wait and retry |
| Competitor content empty | Some sites block scrapers; try a different URL |
| SEMrush/Ahrefs returns no data | Check API key is correct and has credits |
