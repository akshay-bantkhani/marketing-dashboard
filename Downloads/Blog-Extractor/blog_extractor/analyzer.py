"""AI-powered outdated content analyzer — uses Groq (free Llama 3.3 70B) to cross-check blog content."""

import json
import os
import re
from datetime import datetime

import requests as http_requests

CURRENT_YEAR = datetime.now().year
CURRENT_DATE = datetime.now().strftime("%B %d, %Y")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Models tried in order — first available one wins
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
]

SYSTEM_PROMPT = f"""You are an expert content auditor. Today's date is {CURRENT_DATE}.

Your job is to analyze blog content and identify ALL outdated, inaccurate, or stale information. Be thorough — do NOT miss anything.

For each issue found, classify it into one of these categories:
- "Dated Statistic" — old stats, market size numbers, growth rates, survey data referencing past years
- "Outdated Pricing" — tool/product pricing that may have changed
- "Stale Rating" — G2, Capterra, Gartner, Forrester ratings/rankings that change over time
- "Old Company Info" — companies acquired, merged, rebranded, shut down, or significantly changed
- "Expired Projection" — forecasts/projections whose target dates have passed
- "Outdated Tool/Feature" — product features, integrations, or capabilities that may have changed
- "Old Research Citation" — reports, studies, surveys from 2+ years ago
- "Obsolete Technology" — tech references that are no longer current (old AI models, deprecated tools, etc.)
- "Stale Example" — company examples or case studies that no longer reflect current reality
- "Outdated Claim" — any other factual claim that is likely no longer accurate

For severity:
- "high" = definitely outdated or very likely wrong (3+ years old stats, known acquisitions, old pricing)
- "medium" = probably outdated, should be verified (1-2 year old data, claims that change frequently)
- "low" = possibly outdated, worth checking (recent but time-sensitive info)

Return ONLY a valid JSON object with this exact format:
{{"findings": [
  {{
    "type": "category from above",
    "severity": "high/medium/low",
    "match": "the exact outdated text/claim (short key phrase)",
    "context": "the surrounding sentence for reference",
    "issue": "what's wrong with it (be specific)",
    "suggestion": "how to fix it (be actionable)"
  }}
]}}

Be comprehensive. Check EVERYTHING:
1. Year references — any year before {CURRENT_YEAR} in stats, reports, citations
2. Pricing — all dollar amounts for tools/products
3. Ratings & rankings — G2, Capterra, Gartner scores
4. Company info — acquisitions, mergers, rebrandings, shutdowns, leadership changes
5. Market data — market size, CAGR, industry forecasts
6. Tool features — capabilities, integrations, source counts, language support
7. Employee/customer counts — these change constantly
8. Competitor landscape — new entrants, exits, pivots
9. Technology claims — AI models, platforms, tech stacks
10. External links/sources — reports or studies that may be superseded

Return ONLY the JSON object, no markdown fences, no other text. If no issues found, return {{"findings": []}}.
"""


def _extract_text_from_html(container):
    """Get all visible text from a BeautifulSoup element."""
    texts = []
    for el in container.descendants:
        if hasattr(el, 'string') and el.string:
            text = str(el.string).strip()
            if text:
                texts.append(text)
    return "\n".join(texts)


def analyze_content(container, url="", api_key=""):
    """Analyze blog content for outdated information using Groq (Llama 3.3 70B).

    Args:
        container: BeautifulSoup element with the blog content
        url: Source URL for reference
        api_key: Groq API key

    Returns:
        dict with categorized findings
    """
    full_text = _extract_text_from_html(container)

    # Truncate if too long (Groq context limit ~128k but keep reasonable)
    if len(full_text) > 40000:
        full_text = full_text[:40000] + "\n\n[Content truncated...]"

    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {
            "url": url,
            "total_issues": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "error": "Groq API key not provided.",
        }

    last_error = None
    resp = None
    for model in GROQ_MODELS:
        try:
            resp = http_requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Analyze this blog post for outdated information:\n\nURL: {url}\n\n---\n\n{full_text}"},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 8192,
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
            )
            resp.raise_for_status()
            break  # Success — use this model
        except http_requests.exceptions.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code in (400, 404):
                continue  # Model not found — try next
            raise  # Other HTTP error — propagate

    if resp is None:
        raise last_error

    try:

        result = resp.json()
        raw_text = result["choices"][0]["message"]["content"].strip()

        # Clean markdown fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
            raw_text = re.sub(r'\s*```$', '', raw_text)

        parsed = json.loads(raw_text)

        # Handle both {"findings": [...]} and direct [...] formats
        if isinstance(parsed, list):
            findings = parsed
        elif isinstance(parsed, dict) and "findings" in parsed:
            findings = parsed["findings"]
        else:
            findings = []

        # Validate and clean findings
        valid_findings = []
        for f in findings:
            if not isinstance(f, dict):
                continue
            finding = {
                "type": f.get("type", "Outdated Claim"),
                "severity": f.get("severity", "medium"),
                "match": f.get("match", ""),
                "context": f.get("context", ""),
                "issue": f.get("issue", ""),
                "suggestion": f.get("suggestion", ""),
            }
            if finding["match"]:
                valid_findings.append(finding)

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        valid_findings.sort(key=lambda x: severity_order.get(x["severity"], 3))

        high_count = sum(1 for f in valid_findings if f["severity"] == "high")
        medium_count = sum(1 for f in valid_findings if f["severity"] == "medium")
        low_count = sum(1 for f in valid_findings if f["severity"] == "low")

        return {
            "url": url,
            "total_issues": len(valid_findings),
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
            "findings": valid_findings,
        }

    except json.JSONDecodeError:
        return {
            "url": url,
            "total_issues": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "error": "AI returned an invalid response. Please try again.",
        }
    except http_requests.exceptions.HTTPError as e:
        error_msg = str(e)
        try:
            error_body = e.response.json()
            error_msg = error_body.get("error", {}).get("message", str(e))
        except Exception:
            pass
        return {
            "url": url,
            "total_issues": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "error": f"Groq API error: {error_msg}",
        }
    except Exception as e:
        return {
            "url": url,
            "total_issues": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
            "error": str(e),
        }
