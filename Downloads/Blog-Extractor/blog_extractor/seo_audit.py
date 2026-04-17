"""SEO content audit — 3-specialist AI analysis, gap matrix, content verification."""

import json
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse

import requests as http_requests
from bs4 import BeautifulSoup

from .config import HEADERS, SERP_API_URL
from .scraper import extract_page_data, extract_headings, extract_content_text

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
CURRENT_DATE = datetime.now().strftime("%B %d, %Y")


# ── Groq API helper ──────────────────────────────────────────────

def _call_groq(prompt, system_msg, api_key, temperature=0.2, max_tokens=4096):
    """Single Groq API call. Returns parsed JSON dict or raises."""
    resp = http_requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw)


# ── Scraping helpers ──────────────────────────────────────────────

def scrape_competitor_headings(urls):
    """Scrape headings + full content for each URL using a single HTTP request per URL."""
    results = []
    for url in urls:
        try:
            data = extract_page_data(url)
            results.append({
                "url": url,
                "title": data["title"],
                "headings": data["headings"],
                "content": data["content"],
                "error": None,
            })
        except Exception as e:
            results.append({"url": url, "title": "", "headings": [], "content": "", "error": str(e)})
    return results


def full_serp_pipeline(keyword, num_results=6, serp_api_key="",
                       location="", hl="en", gl="us", google_domain="google.com"):
    """Search keyword → scrape top results → return headings + full content."""
    # 1. Search
    serp = search_serp(keyword, serp_api_key, num_results=num_results + 3,
                       location=location, hl=hl, gl=gl, google_domain=google_domain)
    urls = [r["url"] for r in serp.get("results", []) if r.get("url")][:num_results]

    # 2. Scrape each result
    scraped = scrape_competitor_headings(urls)

    return {
        "keyword": keyword,
        "competitors": scraped,
        "ai_overview": serp.get("ai_overview"),
        "featured_snippet": serp.get("featured_snippet"),
        "paa_questions": serp.get("paa_questions", []),
        "related_searches": serp.get("related_searches", []),
        "serp_results": serp.get("results", []),
    }


# ── AI Overview Generator ─────────────────────────────────────────

def generate_ai_overview(keyword, competitor_data, api_key):
    """Use Groq to synthesize an AI Overview from scraped competitor content.

    Mimics what Google's AI Overview does — reads the top-ranking pages and
    generates a comprehensive synthesis: what's covered, what questions are
    answered, patterns, and content gaps.
    """
    # Build a content digest (cap each page at 4000 chars to stay within token limits)
    pages_text = ""
    for i, comp in enumerate(competitor_data[:6], 1):
        content = (comp.get("content") or "").strip()[:4000]
        headings = " | ".join(h["text"] for h in comp.get("headings", [])[:10])
        if not content and not headings:
            continue
        pages_text += f"\n\n--- Result {i}: {comp.get('title', comp.get('url', ''))} ---\n"
        if headings:
            pages_text += f"Headings: {headings}\n"
        if content:
            pages_text += content[:3000]

    if not pages_text.strip():
        return {"error": "No competitor content available to analyze."}

    prompt = f"""You are analyzing the top Google search results for the keyword: "{keyword}"

Here is the content from those pages:
{pages_text}

Generate a comprehensive AI Overview (like Google's AI Overview) that synthesizes what these pages collectively cover.

Return JSON:
{{
  "overview": "3-4 paragraph synthesis of what top-ranking content collectively covers for this keyword",
  "main_topics": ["topic 1", "topic 2", "topic 3"],
  "questions_answered": ["What is X?", "How to Y?"],
  "content_patterns": "What structure, tone, and approach do most top pages share?",
  "unique_angles": ["Angle that appears in only 1-2 pages"],
  "content_gaps": ["Topics missing from all/most results — opportunity to differentiate"],
  "recommended_approach": "1-2 sentences on how to write a better page than these results"
}}"""

    try:
        result = _call_groq(
            prompt,
            "You are an expert content analyst who synthesizes SERP results into actionable AI Overviews. Return only valid JSON.",
            api_key,
            temperature=0.2,
            max_tokens=3000,
        )
        return result
    except Exception as e:
        return {"error": str(e)}


# ── Ahrefs & SEMrush Keyword APIs ────────────────────────────────

def fetch_semrush_keywords(keyword, api_key, database="us", limit=20):
    """Fetch related keywords + main KW data from SEMrush API."""
    results = []

    # Main keyword data
    try:
        resp = http_requests.get(
            "https://api.semrush.com/",
            params={
                "type": "phrase_this",
                "key": api_key,
                "phrase": keyword,
                "database": database,
                "export_columns": "Ph,Nq,Cp,Co,Nr",
            },
            timeout=15,
        )
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        if len(lines) > 1:
            parts = lines[1].split(";")
            if len(parts) >= 2:
                results.append({
                    "keyword": parts[0].strip().strip('"'),
                    "volume": int(re.sub(r"[^\d]", "", parts[1])) if parts[1].strip() else 0,
                    "cpc": float(re.sub(r"[^\d.]", "", parts[2])) if len(parts) > 2 and parts[2].strip() else 0.0,
                    "difficulty": 0,
                    "source": "semrush",
                    "type": "primary",
                })
    except Exception:
        pass

    # Related keywords
    try:
        resp = http_requests.get(
            "https://api.semrush.com/",
            params={
                "type": "phrase_related",
                "key": api_key,
                "phrase": keyword,
                "database": database,
                "display_limit": limit,
                "export_columns": "Ph,Nq,Cp,Co",
            },
            timeout=15,
        )
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        for line in lines[1:]:
            parts = line.split(";")
            if len(parts) >= 2 and parts[0].strip():
                try:
                    results.append({
                        "keyword": parts[0].strip().strip('"'),
                        "volume": int(re.sub(r"[^\d]", "", parts[1])) if parts[1].strip() else 0,
                        "cpc": float(re.sub(r"[^\d.]", "", parts[2])) if len(parts) > 2 and parts[2].strip() else 0.0,
                        "difficulty": 0,
                        "source": "semrush",
                        "type": "related",
                    })
                except Exception:
                    pass
    except Exception:
        pass

    return results


def fetch_ahrefs_keywords(keyword, api_key, country="us", limit=20):
    """Fetch keyword metrics + related keywords from Ahrefs API v3."""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    results = []

    def _parse_cpc(val):
        if isinstance(val, dict):
            return float(val.get("value", 0) or 0)
        return float(val or 0)

    # Main keyword overview
    try:
        resp = http_requests.get(
            "https://api.ahrefs.com/v3/keywords-explorer/overview",
            headers=headers,
            params={
                "country": country,
                "keywords[0]": keyword,
                "select": "volume,keyword_difficulty,cpc",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        for kw in data.get("keywords", []):
            results.append({
                "keyword": kw.get("keyword", keyword),
                "volume": int(kw.get("volume") or 0),
                "difficulty": int(kw.get("keyword_difficulty") or 0),
                "cpc": _parse_cpc(kw.get("cpc")),
                "source": "ahrefs",
                "type": "primary",
            })
    except Exception:
        pass

    # Also-rank-for / related terms
    for endpoint in ["also-rank-for", "related-terms"]:
        try:
            resp = http_requests.get(
                f"https://api.ahrefs.com/v3/keywords-explorer/{endpoint}",
                headers=headers,
                params={
                    "country": country,
                    "keyword": keyword,
                    "limit": limit,
                    "select": "volume,keyword_difficulty,cpc",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for kw in data.get("keywords", []):
                kw_text = kw.get("keyword", "")
                if kw_text:
                    results.append({
                        "keyword": kw_text,
                        "volume": int(kw.get("volume") or 0),
                        "difficulty": int(kw.get("keyword_difficulty") or 0),
                        "cpc": _parse_cpc(kw.get("cpc")),
                        "source": "ahrefs",
                        "type": "related",
                    })
            break  # Use first endpoint that works
        except Exception:
            continue

    return results


def run_keyword_research(keyword, ahrefs_key="", semrush_key="", serp_api_key="",
                         country="us", database="us", num_serp_keywords=3):
    """Full keyword research: SEMrush + Ahrefs + SERP for top-volume keywords.

    Returns:
        keywords: merged list sorted by volume
        serp_results: {keyword: {results, ai_overview, paa, related_searches}}
        related_searches: aggregated related searches (de-duped)
        paa_questions: aggregated PAA questions (de-duped)
        errors: {source: error_msg}
    """
    all_keywords = []
    errors = {}

    if semrush_key:
        try:
            all_keywords.extend(fetch_semrush_keywords(keyword, semrush_key, database=database))
        except Exception as e:
            errors["semrush"] = str(e)

    if ahrefs_key:
        try:
            all_keywords.extend(fetch_ahrefs_keywords(keyword, ahrefs_key, country=country))
        except Exception as e:
            errors["ahrefs"] = str(e)

    # De-duplicate — merge same keyword text, prefer higher volume
    merged: dict = {}
    for kw in all_keywords:
        key = kw["keyword"].lower().strip()
        if key not in merged:
            merged[key] = dict(kw)
        else:
            existing = merged[key]
            if kw["volume"] > existing["volume"]:
                existing["volume"] = kw["volume"]
            if kw["difficulty"] > 0 and existing["difficulty"] == 0:
                existing["difficulty"] = kw["difficulty"]
            if kw["cpc"] > 0 and existing["cpc"] == 0.0:
                existing["cpc"] = kw["cpc"]
            # Mark as both sources
            if kw["source"] != existing["source"]:
                existing["source"] = "ahrefs+semrush"

    merged_keywords = sorted(merged.values(), key=lambda x: -(x.get("volume") or 0))

    # Pick top high-volume keywords to SERP-search
    top_kws = [kw["keyword"] for kw in merged_keywords if (kw.get("volume") or 0) > 0][:num_serp_keywords]
    if keyword.lower() not in [k.lower() for k in top_kws]:
        top_kws.insert(0, keyword)
    top_kws = top_kws[:num_serp_keywords]

    serp_results = {}
    related_searches_all = []
    paa_all = []

    for kw in top_kws:
        try:
            serp = search_serp(kw, api_key=serp_api_key, num_results=6)
            serp_results[kw] = {
                "results": serp.get("results", [])[:6],
                "ai_overview": serp.get("ai_overview"),
                "featured_snippet": serp.get("featured_snippet"),
                "paa_questions": serp.get("paa_questions", []),
                "related_searches": serp.get("related_searches", []),
                "source": serp.get("source", ""),
            }
            paa_all.extend(serp.get("paa_questions", []))
            related_searches_all.extend(serp.get("related_searches", []))
        except Exception as e:
            serp_results[kw] = {"error": str(e), "results": [], "paa_questions": [], "related_searches": []}

    # De-dupe lists
    related_searches_all = list(dict.fromkeys(related_searches_all))[:25]
    paa_all = list(dict.fromkeys(paa_all))[:20]

    return {
        "keyword": keyword,
        "keywords": merged_keywords[:60],
        "top_serp_keywords": top_kws,
        "serp_results": serp_results,
        "related_searches": related_searches_all,
        "paa_questions": paa_all,
        "errors": errors,
    }


# ── Keyword parsing ──────────────────────────────────────────────

def parse_keyword_input(raw_text):
    """Parse keyword data from Semrush paste, CSV, or freeform."""
    keywords = []
    lines = raw_text.strip().split("\n")

    # Detect Semrush CSV header
    header_line = lines[0].lower() if lines else ""
    is_semrush = "keyword" in header_line and ("volume" in header_line or "kd" in header_line)
    if is_semrush:
        lines = lines[1:]  # skip header

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif "," in line and any(c.isdigit() for c in line):
            parts = [p.strip() for p in line.split(",")]
        else:
            parts = [line]

        kw = {"keyword": parts[0], "volume": None, "difficulty": None, "cpc": None, "type": "related"}
        if len(parts) > 1:
            try:
                kw["volume"] = int(re.sub(r"[^\d]", "", parts[1])) if parts[1] else None
            except (ValueError, IndexError):
                pass
        if len(parts) > 2:
            try:
                kw["difficulty"] = float(parts[2]) if parts[2] else None
            except (ValueError, IndexError):
                pass
        if len(parts) > 3:
            try:
                kw["cpc"] = float(re.sub(r"[^\d.]", "", parts[3])) if parts[3] else None
            except (ValueError, IndexError):
                pass
        keywords.append(kw)
    return keywords


def parse_paa_input(raw_text):
    """Parse People Also Ask questions (one per line)."""
    questions = []
    for line in raw_text.strip().split("\n"):
        line = line.strip().lstrip("•-0123456789.) ")
        if line and len(line) > 5:
            questions.append({"keyword": line, "type": "paa"})
    return questions


# ── Free SERP scraping (DuckDuckGo HTML — no API key needed) ─────

_DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _decode_ddg_url(href):
    """Extract the real URL from a DuckDuckGo redirect href."""
    if not href:
        return ""
    if "uddg=" in href:
        try:
            return unquote(href.split("uddg=")[1].split("&")[0])
        except Exception:
            pass
    if href.startswith("http"):
        return href
    return ""


def _ddg_search(keyword, num_results=10):
    """Scrape DuckDuckGo HTML results — free, no API key."""
    resp = http_requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": keyword, "kl": "us-en"},
        headers=_DDG_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    results = []

    # Strategy 1: anchor tags with class result__a (DDG's standard class)
    for a in soup.select("a.result__a"):
        if len(results) >= num_results:
            break
        url = _decode_ddg_url(a.get("href", ""))
        if not url:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        # Walk up to find snippet + domain
        parent = a.find_parent(class_=re.compile(r"result"))
        snippet = domain = ""
        if parent:
            sn = parent.select_one(".result__snippet")
            ur = parent.select_one(".result__url")
            if sn:
                snippet = sn.get_text(strip=True)
            if ur:
                domain = ur.get_text(strip=True)
        if not domain:
            try:
                domain = urlparse(url).netloc
            except Exception:
                pass
        results.append({
            "url": url, "title": title, "snippet": snippet,
            "domain": domain, "position": len(results) + 1,
        })

    # Strategy 2 fallback: any <a> inside a result div that has an http URL
    if not results:
        for div in soup.select("div[class*='result']"):
            if len(results) >= num_results:
                break
            classes = " ".join(div.get("class", []))
            if "ad" in classes or "feedback" in classes:
                continue
            a = div.select_one("h2 a, h3 a, .result__title a")
            if not a:
                continue
            url = _decode_ddg_url(a.get("href", ""))
            if not url:
                continue
            title = a.get_text(strip=True)
            sn = div.select_one(".result__snippet, p")
            snippet = sn.get_text(strip=True) if sn else ""
            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = ""
            if title and url:
                results.append({
                    "url": url, "title": title, "snippet": snippet,
                    "domain": domain, "position": len(results) + 1,
                })

    related = [el.get_text(strip=True) for el in soup.select("a.badge--ad, .related-searches a")][:8]
    return results, related


def _parse_serpapi_response(data, num_results=10):
    """Extract all fields from a SerpAPI JSON response."""
    results = [
        {
            "url": it.get("link", ""),
            "title": it.get("title", ""),
            "snippet": it.get("snippet", ""),
            "domain": it.get("displayed_link", ""),
            "position": i + 1,
        }
        for i, it in enumerate(data.get("organic_results", [])[:num_results])
        if it.get("link")
    ]

    ai_overview = None
    raw_ao = data.get("ai_overview") or data.get("ai_overview_results")
    if raw_ao and isinstance(raw_ao, dict):
        text = raw_ao.get("text") or raw_ao.get("answer") or ""
        sources = [s.get("link", "") for s in raw_ao.get("sources", []) if s.get("link")]
        if text:
            ai_overview = {"text": text, "sources": sources}

    featured_snippet = None
    ab = data.get("answer_box")
    if ab:
        answer = ab.get("answer") or ab.get("snippet") or ab.get("result", "")
        if answer:
            featured_snippet = {
                "title": ab.get("title", ""),
                "answer": answer,
                "source": ab.get("link", ""),
                "type": ab.get("type", ""),
            }

    paa = [p.get("question", "") for p in data.get("related_questions", [])[:10] if p.get("question")]
    related = [r.get("query", "") for r in data.get("related_searches", [])[:8] if r.get("query")]

    return results, ai_overview, featured_snippet, paa, related


def search_serp(keyword, api_key="", num_results=10,
                location="", hl="en", gl="us", google_domain="google.com"):
    """Search SERP.

    Priority:
      1. SerpAPI (when api_key provided) — full data: AI Overview, PAA, location targeting
      2. DuckDuckGo HTML (free fallback, no key needed)
    """

    # ── SerpAPI (primary when key available) ──────────────────────
    if api_key:
        try:
            params = {
                "q": keyword,
                "api_key": api_key,
                "engine": "google",
                "num": num_results + 2,
                "hl": hl or "en",
                "gl": gl or "us",
                "google_domain": google_domain or "google.com",
            }
            if location:
                params["location"] = location
            resp = http_requests.get(SERP_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results, ai_overview, featured_snippet, paa, related = _parse_serpapi_response(data, num_results)
            return {
                "results": results,
                "ai_overview": ai_overview,
                "featured_snippet": featured_snippet,
                "paa_questions": paa,
                "related_searches": related,
                "source": "serpapi",
                "error": None,
            }
        except Exception as e:
            # SerpAPI failed — fall through to DDG
            pass

    # ── DuckDuckGo fallback (no key needed) ───────────────────────
    try:
        results, related = _ddg_search(keyword, num_results)
        return {
            "results": results,
            "ai_overview": None,
            "featured_snippet": None,
            "paa_questions": [],
            "related_searches": related,
            "source": "duckduckgo",
            "error": None if results else "No results found. Try a different keyword.",
        }
    except Exception as e:
        return {
            "results": [], "ai_overview": None, "featured_snippet": None,
            "paa_questions": [], "related_searches": [],
            "source": "none", "error": str(e),
        }


# ── Gap Analysis Matrix ─────────────────────────────────────────

def _normalize_heading(text):
    """Normalize heading text for fuzzy comparison."""
    text = text.lower().strip()
    text = re.sub(r'\b(the|a|an|and|or|of|in|for|to|with|is|are|was|how|what|why|your|our|their)\b', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _headings_similar(h1, h2, threshold=0.55):
    """Check if two headings are semantically similar."""
    n1, n2 = _normalize_heading(h1), _normalize_heading(h2)
    if not n1 or not n2:
        return False
    # Exact or substring match
    if n1 in n2 or n2 in n1:
        return True
    # Fuzzy match
    ratio = SequenceMatcher(None, n1, n2).ratio()
    if ratio >= threshold:
        return True
    # Keyword overlap (words > 3 chars)
    words1 = {w for w in n1.split() if len(w) > 3}
    words2 = {w for w in n2.split() if len(w) > 3}
    if words1 and words2:
        overlap = len(words1 & words2) / min(len(words1), len(words2))
        if overlap >= 0.5:
            return True
    return False


def build_gap_analysis(user_headings, competitor_data):
    """Build a topic gap analysis matrix across user + competitors.

    Returns:
        {"topics": [...], "summary": {...}}
    """
    # Collect all H2-level headings (main sections)
    all_headings = []
    # User headings
    for h in user_headings:
        if h["level"] in (1, 2):
            all_headings.append({"text": h["text"], "source": "user", "comp_idx": -1})
    # Competitor headings
    for ci, comp in enumerate(competitor_data):
        for h in comp.get("headings", []):
            if h["level"] in (1, 2):
                all_headings.append({"text": h["text"], "source": "competitor", "comp_idx": ci})

    # Group into topics using fuzzy matching
    topics = []
    used = set()

    for i, h in enumerate(all_headings):
        if i in used:
            continue
        topic = {
            "topic": h["text"],
            "user_has": h["source"] == "user",
            "competitors_with": [],
            "original_headings": {},
        }
        if h["source"] == "user":
            topic["original_headings"]["user"] = h["text"]
        else:
            topic["competitors_with"].append(h["comp_idx"])
            topic["original_headings"][f"comp_{h['comp_idx']}"] = h["text"]
        used.add(i)

        # Find similar headings
        for j, h2 in enumerate(all_headings):
            if j in used:
                continue
            if _headings_similar(h["text"], h2["text"]):
                used.add(j)
                if h2["source"] == "user":
                    topic["user_has"] = True
                    topic["original_headings"]["user"] = h2["text"]
                elif h2["comp_idx"] not in topic["competitors_with"]:
                    topic["competitors_with"].append(h2["comp_idx"])
                    topic["original_headings"][f"comp_{h2['comp_idx']}"] = h2["text"]

        topic["frequency"] = len(topic["competitors_with"])
        num_competitors = len(competitor_data)
        threshold = max(2, num_competitors * 0.6)

        if not topic["user_has"] and topic["frequency"] >= threshold:
            topic["category"] = "must_have"
        elif not topic["user_has"] and topic["frequency"] > 0:
            topic["category"] = "gap"
        elif topic["user_has"] and topic["frequency"] == 0:
            topic["category"] = "strength"
        else:
            topic["category"] = "common"

        topics.append(topic)

    # Sort: must_have first, then gaps, then common, then strengths
    cat_order = {"must_have": 0, "gap": 1, "common": 2, "strength": 3}
    topics.sort(key=lambda t: (cat_order.get(t["category"], 9), -t["frequency"]))

    summary = {
        "total_topics": len(topics),
        "must_haves": sum(1 for t in topics if t["category"] == "must_have"),
        "gaps": sum(1 for t in topics if t["category"] == "gap"),
        "common": sum(1 for t in topics if t["category"] == "common"),
        "strengths": sum(1 for t in topics if t["category"] == "strength"),
    }

    return {"topics": topics, "summary": summary, "num_competitors": len(competitor_data)}


# ── 3-Specialist AI Recommendation ──────────────────────────────

def _build_context(user_headings, competitor_data, keywords):
    """Build shared context strings for specialist prompts."""
    user_text = "\n".join(f"{'  ' * (h['level']-1)}H{h['level']}: {h['text']}" for h in user_headings) or "(No headings)"

    comp_text = ""
    for i, comp in enumerate(competitor_data, 1):
        comp_text += f"\n--- Competitor {i}: {comp.get('title', comp['url'])} ---\n"
        for h in comp.get("headings", []):
            comp_text += f"{'  ' * (h['level']-1)}H{h['level']}: {h['text']}\n"

    kw_text = "\n".join(f"- {kw['keyword']} (vol: {kw.get('volume', '?')})" for kw in keywords[:25]) or "(No keywords)"

    paa_items = [kw for kw in keywords if kw.get("type") == "paa"]
    paa_text = "\n".join(f"- {p['keyword']}" for p in paa_items) if paa_items else "(No PAA data)"

    return user_text, comp_text, kw_text, paa_text


def generate_heading_recommendation(user_headings, competitor_data, keywords, guidelines, api_key):
    """Run 3 specialist analyses + synthesis to produce optimal heading structure."""

    user_text, comp_text, kw_text, paa_text = _build_context(user_headings, competitor_data, keywords)
    guide_text = "\n".join(f"- {g['title']}: {g['content']}" for g in guidelines) or "(No guidelines)"

    shared_context = f"""
## User's Current Blog Headings:
{user_text}

## Competitor Heading Structures (top 6 ranking pages):
{comp_text}

## Target Keywords:
{kw_text}

## People Also Ask:
{paa_text}
"""

    analyses = {}
    errors = []

    # ── Specialist 1: Content Strategist ──
    try:
        content_result = _call_groq(
            f"""Analyze these blog heading structures as a Content Strategy Specialist. Today is {CURRENT_DATE}.
{shared_context}

Evaluate:
1. Information architecture — is the content logically organized?
2. Content depth — which topics need deeper coverage?
3. Reader flow — does the structure guide the reader well?
4. Missing perspectives — what viewpoints/angles are missing?
5. Storytelling — is there a compelling narrative arc?

Return JSON:
{{
  "topics_to_add": [{{"text": "heading text", "reason": "why add this", "priority": "high/medium/low"}}],
  "topics_to_keep": [{{"text": "current heading", "reason": "why keep"}}],
  "topics_to_reword": [{{"current": "old text", "suggested": "new text", "reason": "why reword"}}],
  "topics_to_remove": [{{"text": "heading to remove", "reason": "why remove"}}],
  "content_depth_notes": "Overall assessment of content depth vs competitors",
  "reader_flow_score": 1-10
}}""",
            "You are a Content Strategy Specialist with 15 years of experience in B2B content marketing. You focus on information architecture, content depth, readability, and storytelling. Return only valid JSON.",
            api_key
        )
        analyses["content"] = content_result
    except Exception as e:
        errors.append(f"Content Specialist: {e}")

    time.sleep(1)  # Rate limit buffer

    # ── Specialist 2: PMM Specialist ──
    try:
        pmm_result = _call_groq(
            f"""Analyze these blog heading structures as a Product Marketing Manager. Today is {CURRENT_DATE}.
{shared_context}

Evaluate:
1. Product positioning — how well does the structure showcase the product vs competitors?
2. Buyer journey alignment — does it address awareness, consideration, and decision stages?
3. Value propositions — are unique selling points clearly structured?
4. Competitive differentiation — does the structure highlight what makes this product different?
5. Trust signals — are there sections for social proof, case studies, comparisons?

Return JSON:
{{
  "topics_to_add": [{{"text": "heading text", "reason": "why add — buyer journey stage it serves", "priority": "high/medium/low"}}],
  "topics_to_keep": [{{"text": "current heading", "reason": "why keep — positioning value"}}],
  "topics_to_reword": [{{"current": "old text", "suggested": "new text", "reason": "better positioning"}}],
  "topics_to_remove": [{{"text": "heading to remove", "reason": "why remove — positioning risk"}}],
  "positioning_notes": "How well the blog positions the product vs competitors",
  "buyer_journey_coverage": {{"awareness": "good/weak/missing", "consideration": "good/weak/missing", "decision": "good/weak/missing"}}
}}""",
            "You are a Product Marketing Manager (PMM) with deep expertise in B2B SaaS positioning, competitive battlecards, and buyer journey mapping. Return only valid JSON.",
            api_key
        )
        analyses["pmm"] = pmm_result
    except Exception as e:
        errors.append(f"PMM Specialist: {e}")

    time.sleep(1)

    # ── Specialist 3: SEO Specialist ──
    try:
        seo_result = _call_groq(
            f"""Analyze these blog heading structures as a Technical SEO Specialist. Today is {CURRENT_DATE}.
{shared_context}

Evaluate:
1. Keyword optimization — are target keywords naturally placed in headings?
2. Search intent matching — do headings match informational/commercial/transactional intent?
3. Featured snippet opportunities — which headings could win Position 0 (definitions, lists, comparisons)?
4. SERP coverage — does the structure cover enough related queries to build topical authority?
5. Internal linking opportunities — which sections could link to related content?
6. Content freshness signals — do headings include year/date references where appropriate?

Return JSON:
{{
  "topics_to_add": [{{"text": "heading text with keyword", "reason": "targets keyword X (vol: Y)", "priority": "high/medium/low", "search_intent": "informational/commercial/transactional"}}],
  "topics_to_keep": [{{"text": "current heading", "reason": "already optimized for keyword X"}}],
  "topics_to_reword": [{{"current": "old text", "suggested": "new text with keyword", "reason": "better keyword placement"}}],
  "topics_to_remove": [{{"text": "heading to remove", "reason": "cannibalizes/dilutes"}}],
  "featured_snippet_opportunities": ["heading texts that could win featured snippets"],
  "keyword_coverage_score": 1-10
}}""",
            "You are a Technical SEO Specialist who has ranked hundreds of B2B pages on page 1 of Google. You think in terms of search intent, featured snippets, topical authority, and keyword clustering. Return only valid JSON.",
            api_key
        )
        analyses["seo"] = seo_result
    except Exception as e:
        errors.append(f"SEO Specialist: {e}")

    time.sleep(1)

    if not analyses:
        return {"recommendations": [], "summary": "", "specialist_analyses": {}, "paa_questions": [],
                "error": "All specialist analyses failed: " + "; ".join(errors)}

    # ── Synthesis: Merge all 3 specialist outputs ──
    try:
        synthesis_input = json.dumps(analyses, indent=2)
        synthesis = _call_groq(
            f"""You have received analyses from 3 specialists about a blog's heading structure. Today is {CURRENT_DATE}.

## Specialist Analyses:
{synthesis_input}

## User's Current Headings:
{user_text}

## Content Guidelines:
{guide_text}

## Your Task:
Synthesize all 3 specialist perspectives into ONE optimal heading structure.

For each heading, assign a CONFIDENCE score:
- 90-100: All 3 specialists agree
- 70-89: 2 out of 3 specialists agree
- 50-69: Only 1 specialist recommends, but it's important
- Below 50: Speculative/nice-to-have

Classify each heading's diff_status:
- "keep": Exists in user's current headings, all specialists agree to keep
- "reword": Exists but should be reworded (show both old and new text)
- "new": Content gap — doesn't exist in user's blog, should be added
- "remove": Exists in user's blog but specialists recommend removing

Return JSON:
{{
  "recommendations": [
    {{
      "level": 1-4,
      "text": "Final heading text",
      "original_text": "Original heading if reworded, null if new",
      "is_gap": true/false,
      "diff_status": "keep/reword/new/remove",
      "confidence": 50-100,
      "reason": "Combined reason from specialists",
      "specialist_sources": ["content", "pmm", "seo"]
    }}
  ],
  "summary": "3-4 sentence synthesis of all specialist findings",
  "paa_questions": ["People Also Ask questions the content should address"],
  "key_insights": {{
    "content": "1-sentence key insight from Content Specialist",
    "pmm": "1-sentence key insight from PMM",
    "seo": "1-sentence key insight from SEO Specialist"
  }}
}}""",
            "You are a Chief Content Officer synthesizing 3 specialist analyses into one actionable plan. Be decisive — pick the best recommendations, resolve conflicts, and produce a clear final structure. Return only valid JSON.",
            api_key, max_tokens=6000
        )

        recs = synthesis.get("recommendations", [])
        summary = synthesis.get("summary", "")
        paa = synthesis.get("paa_questions", [])
        key_insights = synthesis.get("key_insights", {})

        return {
            "recommendations": recs,
            "summary": summary,
            "paa_questions": paa,
            "specialist_analyses": analyses,
            "key_insights": key_insights,
            "errors": errors if errors else None,
            "error": None,
        }

    except Exception as e:
        # If synthesis fails, try to build recommendations from individual specialist outputs
        fallback_recs = _build_fallback_recs(analyses, user_headings)
        return {
            "recommendations": fallback_recs,
            "summary": f"Synthesis failed ({e}). Showing combined specialist recommendations.",
            "paa_questions": [],
            "specialist_analyses": analyses,
            "key_insights": {},
            "errors": errors + [f"Synthesis: {e}"],
            "error": None,
        }


def _build_fallback_recs(analyses, user_headings):
    """Build fallback recommendations if synthesis call fails."""
    recs = []
    seen = set()

    # Keep existing headings
    for h in user_headings:
        recs.append({"level": h["level"], "text": h["text"], "is_gap": False,
                      "diff_status": "keep", "confidence": 70, "reason": "Existing heading"})
        seen.add(_normalize_heading(h["text"]))

    # Add topics from all specialists
    for source, analysis in analyses.items():
        for item in analysis.get("topics_to_add", []):
            normalized = _normalize_heading(item.get("text", ""))
            if normalized not in seen and item.get("text"):
                recs.append({
                    "level": 2, "text": item["text"], "is_gap": True,
                    "diff_status": "new", "confidence": 60,
                    "reason": f"[{source}] {item.get('reason', '')}",
                })
                seen.add(normalized)

    return recs


# ── Content Plan Generation ──────────────────────────────────────

def generate_content_plan(audit_data, api_key):
    audit = audit_data["audit"]
    recs = [r for r in audit_data["recommendations"] if r.get("status") != "rejected"]
    keywords = audit_data["keywords"]

    final_headings = []
    for r in recs:
        final_headings.append({
            "level": r["heading_level"], "text": r["heading_text"],
            "is_gap": bool(r.get("is_gap")), "reason": r.get("change_reason", ""),
            "notes": r.get("user_notes", ""), "status": r.get("status", "pending"),
        })

    kw_list = [{"keyword": k["keyword"], "volume": k.get("search_volume"), "difficulty": k.get("keyword_difficulty")} for k in keywords]
    heading_text = "\n".join(f"{'  ' * (h['level']-1)}H{h['level']}: {h['text']} {'[GAP]' if h['is_gap'] else ''}" for h in final_headings)
    kw_text = "\n".join(f"- {k['keyword']} (vol: {k.get('volume', '?')})" for k in kw_list[:20])

    paa_items = [k for k in keywords if k.get("keyword_type") == "paa"]
    paa_text = "\n".join(f"- {p['keyword']}" for p in paa_items) if paa_items else ""

    guide_text = "\n".join(f"- {g['title']}: {g['content']}" for g in audit_data.get("guidelines", []))

    prompt = f"""Create a detailed content plan for this blog post. Act as a combined Content Specialist, PMM, and SEO expert.

Blog URL: {audit.get('blog_url', '')}
Target Keyword: {audit.get('target_keyword', '')}

Final Heading Structure:
{heading_text}

Keywords to Target:
{kw_text}

People Also Ask Questions to Address:
{paa_text or "(none)"}

Content Guidelines:
{guide_text or "(none)"}

For each heading section, provide:
1. Key points to cover (3-5 bullets) — be specific and actionable
2. Which keywords to naturally include in that section
3. Word count suggestion
4. Whether this section should include: comparison table, list, definition, example, stats, or CTA

Return JSON:
{{
  "title": "SEO-optimized blog title (include primary keyword)",
  "target_keyword": "primary keyword",
  "total_word_count": 3500,
  "sections": [
    {{
      "heading": "H2: Section Name",
      "key_points": ["specific point 1", "specific point 2", "specific point 3"],
      "keywords_to_include": ["kw1", "kw2"],
      "word_count": 300,
      "is_gap": false,
      "content_type": "comparison_table/list/definition/narrative/stats",
      "paa_to_address": "PAA question this section answers (if any)",
      "notes": "additional guidance"
    }}
  ],
  "meta_title": "SEO meta title (under 60 chars, include keyword)",
  "meta_description": "SEO meta description (under 155 chars, include keyword + CTA)"
}}"""

    try:
        plan = _call_groq(prompt, "You are a senior content strategist. Create actionable, specific content plans. Return only valid JSON.", api_key, max_tokens=6000)
        plan["generated_at"] = datetime.now().isoformat()
        plan["audit_id"] = audit.get("id")
        return {"plan": plan, "error": None}
    except Exception as e:
        return {
            "plan": {
                "title": audit.get("blog_title", ""),
                "target_keyword": audit.get("target_keyword", ""),
                "sections": [{"heading": f"H{h['level']}: {h['text']}", "is_gap": h["is_gap"], "notes": h.get("notes", "")} for h in final_headings],
                "generated_at": datetime.now().isoformat(),
                "audit_id": audit.get("id"),
            },
            "error": str(e),
        }
