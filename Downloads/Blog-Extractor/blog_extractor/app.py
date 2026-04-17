"""Flask web UI for the blog extractor."""

import io
import json
import os
import re
import zipfile

from flask import Flask, render_template_string, request, send_file, send_from_directory, jsonify

from .analyzer import analyze_content
from .cleaner import clean_content
from .config import DEFAULT_OUTPUT_DIR
from .converter import DocxBuilder, add_hyperlink, process_element
from .database import (
    init_db, create_audit, get_audit, update_audit, list_audits,
    save_keywords, get_keywords, save_competitor, get_competitors, delete_competitors,
    save_headings, get_headings, get_all_competitor_headings,
    save_recommendations, get_recommendations, update_recommendation, delete_recommendation, add_recommendation,
    save_guideline, get_guidelines, update_guideline, delete_guideline,
    save_plan, get_plan,
    save_content_verification, get_content_verification,
    save_specialist_analyses, get_specialist_analyses,
)
from .scraper import extract_headings, extract_title, fetch_page, find_article_content, parse_html
from .seo_audit import (
    scrape_competitor_headings, parse_keyword_input, parse_paa_input,
    generate_heading_recommendation, generate_content_plan, search_serp,
    build_gap_analysis, full_serp_pipeline, generate_ai_overview,
    run_keyword_research,
)

app = Flask(__name__)

# Initialize database on import
init_db()


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify(success=False, error=str(e)), 500

# Resolve output dir relative to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, DEFAULT_OUTPUT_DIR)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Blog Extractor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 48px 24px; }
        h1 { font-size: 28px; font-weight: 700; margin-bottom: 4px; color: #f8fafc; }
        .subtitle { color: #94a3b8; margin-bottom: 24px; font-size: 14px; }

        /* Tabs */
        .tabs { display: flex; gap: 0; margin-bottom: 28px; border-bottom: 2px solid #1e293b; flex-wrap: wrap; }
        .tab {
            padding: 12px 28px; font-size: 14px; font-weight: 600;
            cursor: pointer; border: none; background: none; color: #64748b;
            border-bottom: 2px solid transparent; margin-bottom: -2px;
            transition: all 0.2s;
        }
        .tab:hover { color: #94a3b8; }
        .tab.active { color: #3b82f6; border-bottom-color: #3b82f6; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .input-group { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
        textarea {
            width: 100%; min-height: 120px; padding: 14px 16px;
            background: #1e293b; border: 1px solid #334155; border-radius: 10px;
            color: #f1f5f9; font-size: 14px; font-family: 'JetBrains Mono', monospace;
            resize: vertical; outline: none; transition: border-color 0.2s;
        }
        textarea:focus { border-color: #3b82f6; }
        textarea::placeholder { color: #64748b; }
        input[type="password"], input[type="text"], input[type="number"], select {
            width: 100%; padding: 12px 16px;
            background: #1e293b; border: 1px solid #334155; border-radius: 10px;
            color: #f1f5f9; font-size: 14px; font-family: 'JetBrains Mono', monospace;
            outline: none; transition: border-color 0.2s;
        }
        input[type="password"]:focus, input[type="text"]:focus { border-color: #3b82f6; }
        input::placeholder { color: #64748b; }
        select { cursor: pointer; }
        .field-label { color: #94a3b8; font-size: 13px; font-weight: 600; margin-bottom: 6px; display: block; }
        .btn {
            padding: 12px 28px; border: none; border-radius: 10px;
            font-size: 15px; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px;
        }
        .btn-primary { background: #3b82f6; color: #fff; }
        .btn-primary:hover { background: #2563eb; transform: translateY(-1px); }
        .btn-primary:disabled { background: #334155; color: #64748b; cursor: not-allowed; transform: none; }
        .btn-orange { background: #ea580c; color: #fff; }
        .btn-orange:hover { background: #c2410c; transform: translateY(-1px); }
        .btn-orange:disabled { background: #334155; color: #64748b; cursor: not-allowed; transform: none; }
        .btn-green { background: #059669; color: #fff; }
        .btn-green:hover { background: #047857; transform: translateY(-1px); }
        .btn-green:disabled { background: #334155; color: #64748b; cursor: not-allowed; transform: none; }
        .btn-sm { padding: 6px 14px; font-size: 12px; border-radius: 6px; }
        .btn-danger { background: #dc2626; color: #fff; }
        .btn-danger:hover { background: #b91c1c; }
        .btn-ghost { background: transparent; border: 1px solid #334155; color: #94a3b8; }
        .btn-ghost:hover { background: #1e293b; color: #e2e8f0; }
        .status { margin-top: 20px; padding: 16px; border-radius: 10px; display: none; font-size: 14px; }
        .status.loading { display: block; background: #1e293b; border: 1px solid #334155; color: #94a3b8; }
        .status.success { display: block; background: #052e16; border: 1px solid #166534; color: #4ade80; }
        .status.error { display: block; background: #350a0a; border: 1px solid #7f1d1d; color: #f87171; }
        .results { margin-top: 24px; display: flex; flex-direction: column; gap: 10px; }
        .result-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 14px 16px; background: #1e293b; border: 1px solid #334155; border-radius: 10px;
        }
        .result-title { font-size: 14px; color: #e2e8f0; flex: 1; margin-right: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .btn-download { background: #059669; color: #fff; padding: 8px 18px; font-size: 13px; border-radius: 8px; text-decoration: none; }
        .btn-download:hover { background: #047857; }
        .btn-download-all {
            background: #7c3aed; color: #fff; padding: 14px 32px; font-size: 15px;
            border-radius: 10px; text-decoration: none; font-weight: 600;
            display: none; margin-top: 16px; text-align: center; cursor: pointer; border: none;
            transition: all 0.2s;
        }
        .btn-download-all:hover { background: #6d28d9; transform: translateY(-1px); }
        .spinner { width: 18px; height: 18px; border: 2px solid #64748b; border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.6s linear infinite; display: inline-block; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hint { color: #64748b; font-size: 12px; margin-bottom: 24px; }

        /* Audit report styles */
        .audit-report { margin-top: 24px; }
        .audit-url-block { margin-bottom: 28px; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; }
        .audit-url-header {
            padding: 16px 20px; display: flex; justify-content: space-between; align-items: center;
            background: #1e293b; border-bottom: 1px solid #334155; cursor: pointer;
        }
        .audit-url-header:hover { background: #253349; }
        .audit-url-title { font-size: 15px; font-weight: 600; color: #f1f5f9; }
        .audit-badges { display: flex; gap: 8px; flex-shrink: 0; }
        .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
        .badge-high { background: #7f1d1d; color: #fca5a5; }
        .badge-medium { background: #713f12; color: #fde68a; }
        .badge-low { background: #14532d; color: #86efac; }
        .badge-clean { background: #052e16; color: #4ade80; }
        .badge-gap { background: #7c2d12; color: #fdba74; }
        .badge-keep { background: #14532d; color: #86efac; }
        .audit-findings { padding: 0 20px 20px; }
        .finding-item {
            padding: 16px 18px; margin-top: 14px; border-radius: 10px;
            border-left: 4px solid; background: #0f172a;
        }
        .finding-item.high { border-left-color: #ef4444; }
        .finding-item.medium { border-left-color: #f59e0b; }
        .finding-item.low { border-left-color: #22c55e; }
        .finding-type {
            display: inline-block; font-size: 11px; font-weight: 700; text-transform: uppercase;
            letter-spacing: 0.5px; margin-bottom: 8px; padding: 3px 8px; border-radius: 4px;
        }
        .finding-type.high { background: #450a0a; color: #fca5a5; }
        .finding-type.medium { background: #451a03; color: #fde68a; }
        .finding-type.low { background: #052e16; color: #86efac; }
        .finding-match {
            font-family: 'JetBrains Mono', monospace; font-size: 13px;
            color: #f8fafc; margin: 8px 0; font-weight: 600;
            background: #1e293b; padding: 8px 12px; border-radius: 6px;
        }
        .finding-context { font-size: 13px; color: #94a3b8; margin: 6px 0; line-height: 1.6; }
        .finding-issue { font-size: 13px; color: #fb923c; margin: 8px 0; line-height: 1.5; }
        .finding-issue::before { content: "Issue: "; font-weight: 700; color: #f97316; }
        .finding-suggestion { font-size: 13px; color: #67e8f9; margin-top: 8px; line-height: 1.5; }
        .finding-suggestion::before { content: "Fix: "; font-weight: 700; color: #22d3ee; }
        .summary-bar {
            display: flex; gap: 16px; padding: 16px 20px; background: #1e293b;
            border-radius: 10px; margin-bottom: 20px; border: 1px solid #334155;
        }
        .summary-stat { text-align: center; flex: 1; }
        .summary-stat .num { font-size: 28px; font-weight: 700; }
        .summary-stat .label { font-size: 12px; color: #94a3b8; margin-top: 2px; }
        .num-high { color: #ef4444; }
        .num-medium { color: #f59e0b; }
        .num-low { color: #22c55e; }
        .num-total { color: #3b82f6; }
        .api-key-section { margin-bottom: 20px; }
        .api-key-saved { color: #4ade80; font-size: 12px; margin-top: 4px; display: none; }
        .powered-by { color: #475569; font-size: 11px; margin-top: 6px; }

        /* SEO Audit Styles */
        .seo-container { max-width: 100%; }
        .step-wizard { display: flex; gap: 4px; margin-bottom: 32px; }
        .step-indicator {
            flex: 1; padding: 12px 8px; text-align: center; font-size: 12px; font-weight: 600;
            background: #1e293b; border: 1px solid #334155; color: #64748b;
            cursor: pointer; transition: all 0.2s;
        }
        .step-indicator:first-child { border-radius: 10px 0 0 10px; }
        .step-indicator:last-child { border-radius: 0 10px 10px 0; }
        .step-indicator.active { background: #1e3a5f; border-color: #3b82f6; color: #3b82f6; }
        .step-indicator.completed { background: #052e16; border-color: #166534; color: #4ade80; }
        .step-content { display: none; }
        .step-content.active { display: block; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
        .card-title { font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 16px; }

        /* Heading grid */
        .heading-grid { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 12px; }
        .heading-column {
            min-width: 220px; max-width: 280px; flex-shrink: 0;
            background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 16px;
        }
        .heading-column.user-col { border-color: #3b82f6; border-width: 2px; }
        .col-title { font-size: 13px; font-weight: 700; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .col-title.user-label { color: #3b82f6; }
        .h-item { margin-bottom: 6px; line-height: 1.4; }
        .h-item.h1 { font-size: 14px; color: #f8fafc; font-weight: 700; }
        .h-item.h2 { font-size: 13px; color: #e2e8f0; font-weight: 600; padding-left: 12px; }
        .h-item.h3 { font-size: 12px; color: #94a3b8; padding-left: 24px; }
        .h-item.h4 { font-size: 11px; color: #64748b; padding-left: 36px; }
        .h-item.h5 { font-size: 11px; color: #475569; padding-left: 48px; font-style: italic; }
        .h-item.h6 { font-size: 10px; color: #374151; padding-left: 52px; border-left: 2px solid #374151; }
        .h-level { font-size: 10px; color: #475569; margin-right: 4px; }
        /* Keyword Research */
        .kw-table { width: 100%; border-collapse: collapse; font-size: 12px; }
        .kw-table th { text-align: left; padding: 6px 10px; color: #64748b; border-bottom: 1px solid #334155; }
        .kw-table td { padding: 5px 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0; }
        .kw-table tr:hover td { background: #1e293b; }
        .kw-source { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px; }
        .kw-src-ahrefs { background: #1e3a5f; color: #60a5fa; }
        .kw-src-semrush { background: #064e3b; color: #34d399; }
        .kw-src-both { background: #3b1d5f; color: #a78bfa; }
        .kw-primary-badge { font-size: 10px; background: #172554; color: #93c5fd; padding: 1px 5px; border-radius: 3px; margin-left: 4px; }
        .serp-kw-block { background: #0a0f1a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
        .serp-kw-title { font-size: 12px; font-weight: 700; color: #3b82f6; margin-bottom: 8px; }

        /* Recommendation comparison */
        .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .compare-col { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 20px; }
        .compare-col.recommended { border-color: #059669; }
        .rec-item {
            display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; margin-bottom: 8px;
            background: #1e293b; border-radius: 8px; border-left: 3px solid #334155;
        }
        .rec-item.gap { border-left-color: #ea580c; background: #1c1209; }
        .rec-item.keep { border-left-color: #059669; }
        .rec-reason { font-size: 11px; color: #94a3b8; margin-top: 4px; }

        /* Editable framework */
        .edit-item {
            display: flex; align-items: flex-start; gap: 10px; padding: 14px;
            background: #0f172a; border: 1px solid #334155; border-radius: 10px; margin-bottom: 10px;
            transition: border-color 0.2s;
        }
        .edit-item.accepted { border-color: #166534; }
        .edit-item.rejected { border-color: #7f1d1d; opacity: 0.5; }
        .edit-item select { width: 70px; padding: 6px 8px; font-size: 12px; }
        .edit-item input[type="text"] { flex: 1; padding: 8px 12px; font-size: 13px; }
        .edit-actions { display: flex; gap: 6px; flex-shrink: 0; }
        .edit-notes { width: 100%; margin-top: 8px; min-height: 40px; font-size: 12px; padding: 8px; }

        /* Plan display */
        .plan-section {
            padding: 16px 20px; margin-bottom: 12px;
            background: #0f172a; border: 1px solid #334155; border-radius: 10px;
        }
        .plan-section.gap-section { border-left: 3px solid #ea580c; }
        .plan-heading { font-size: 15px; font-weight: 700; color: #f8fafc; margin-bottom: 8px; }
        .plan-points { list-style: disc; padding-left: 20px; }
        .plan-points li { font-size: 13px; color: #cbd5e1; margin-bottom: 4px; line-height: 1.5; }
        .plan-kw { font-size: 12px; color: #67e8f9; margin-top: 6px; }
        .plan-wc { font-size: 12px; color: #94a3b8; margin-top: 4px; }
        .plan-meta { background: #1e293b; padding: 16px 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #334155; }
        .plan-meta-item { font-size: 13px; color: #cbd5e1; margin-bottom: 6px; }
        .plan-meta-label { font-weight: 700; color: #94a3b8; }

        /* Guidelines */
        .guideline-item {
            padding: 14px 16px; background: #0f172a; border: 1px solid #334155;
            border-radius: 10px; margin-bottom: 10px;
        }
        .guideline-title { font-size: 14px; font-weight: 600; color: #f8fafc; margin-bottom: 4px; }
        .guideline-content { font-size: 13px; color: #94a3b8; line-height: 1.5; }
        .guideline-cat { font-size: 11px; color: #64748b; margin-top: 6px; text-transform: uppercase; }

        /* History sidebar */
        .audit-history { margin-bottom: 24px; }
        .audit-history-item {
            padding: 12px 16px; background: #1e293b; border: 1px solid #334155;
            border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;
        }
        .audit-history-item:hover { border-color: #3b82f6; }
        .audit-history-title { font-size: 13px; font-weight: 600; color: #e2e8f0; }
        .audit-history-meta { font-size: 11px; color: #64748b; margin-top: 4px; }

        /* Gap Analysis Matrix */
        .gap-matrix { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
        .gap-matrix th, .gap-matrix td { padding: 8px 10px; border: 1px solid #334155; text-align: center; }
        .gap-matrix th { background: #0f172a; color: #94a3b8; font-weight: 600; font-size: 11px; }
        .gap-matrix td:first-child { text-align: left; font-weight: 500; color: #e2e8f0; min-width: 180px; }
        .gap-matrix .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
        .gap-matrix .dot.present { background: #4ade80; }
        .gap-matrix .dot.absent { background: #334155; }
        .gap-row-must-have { background: #1c1209 !important; }
        .gap-row-gap { background: #170d07 !important; }
        .gap-row-strength { background: #05200e !important; }
        .gap-category { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 6px; border-radius: 4px; }
        .gap-cat-must_have { background: #7c2d12; color: #fdba74; }
        .gap-cat-gap { background: #451a03; color: #fde68a; }
        .gap-cat-strength { background: #052e16; color: #86efac; }
        .gap-cat-common { background: #1e293b; color: #94a3b8; }

        /* Diff view */
        .diff-item {
            display: flex; align-items: flex-start; gap: 12px; padding: 12px 16px;
            margin-bottom: 8px; border-radius: 10px; border-left: 4px solid;
            background: #0f172a;
        }
        .diff-keep { border-left-color: #059669; }
        .diff-reword { border-left-color: #3b82f6; }
        .diff-new { border-left-color: #ea580c; }
        .diff-remove { border-left-color: #dc2626; opacity: 0.7; }
        .diff-badge {
            font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 8px;
            border-radius: 4px; flex-shrink: 0; letter-spacing: 0.5px;
        }
        .diff-badge-keep { background: #052e16; color: #4ade80; }
        .diff-badge-reword { background: #172554; color: #93c5fd; }
        .diff-badge-new { background: #431407; color: #fdba74; }
        .diff-badge-remove { background: #450a0a; color: #fca5a5; }
        .confidence-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #1e293b; color: #94a3b8; margin-left: 8px; }
        .confidence-high { color: #4ade80; }
        .confidence-medium { color: #fde68a; }
        .confidence-low { color: #fca5a5; }
        .diff-original { text-decoration: line-through; color: #64748b; font-size: 12px; }
        .diff-arrow { color: #64748b; margin: 0 6px; }

        /* Specialist insights */
        .specialist-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }
        .specialist-card {
            background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 16px;
            border-top: 3px solid;
        }
        .specialist-card.content-spec { border-top-color: #8b5cf6; }
        .specialist-card.pmm-spec { border-top-color: #f59e0b; }
        .specialist-card.seo-spec { border-top-color: #06b6d4; }
        .specialist-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .specialist-label.content-spec { color: #a78bfa; }
        .specialist-label.pmm-spec { color: #fbbf24; }
        .specialist-label.seo-spec { color: #22d3ee; }
        .specialist-insight { font-size: 13px; color: #cbd5e1; line-height: 1.5; }

        /* SERP Research */
        .serp-ai-overview {
            background: linear-gradient(135deg, #1c1a07, #1a1207); border: 1px solid #713f12;
            border-left: 4px solid #f59e0b; border-radius: 10px; padding: 16px; margin-bottom: 14px;
        }
        .serp-ai-label { font-size: 11px; font-weight: 700; color: #fbbf24; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
        .serp-ai-text { font-size: 13px; color: #fde68a; line-height: 1.65; }
        .serp-ai-sources { margin-top: 8px; font-size: 11px; color: #92400e; }
        .serp-featured {
            background: #0f1e2e; border: 1px solid #1e40af; border-left: 4px solid #3b82f6;
            border-radius: 10px; padding: 14px; margin-bottom: 14px;
        }
        .serp-featured-label { font-size: 11px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
        .serp-result-item {
            display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px;
            border: 1px solid #1e293b; border-radius: 8px; margin-bottom: 8px;
            background: #0f172a; transition: border-color 0.15s;
        }
        .serp-result-item:hover { border-color: #334155; }
        .serp-pos { font-size: 12px; font-weight: 700; color: #475569; min-width: 22px; padding-top: 2px; }
        .serp-result-body { flex: 1; min-width: 0; }
        .serp-result-title { font-size: 14px; color: #60a5fa; font-weight: 600; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .serp-result-domain { font-size: 11px; color: #4ade80; margin-bottom: 4px; }
        .serp-result-snippet { font-size: 12px; color: #94a3b8; line-height: 1.5; }
        .serp-add-btn { font-size: 11px; padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; background: none; color: #64748b; cursor: pointer; flex-shrink: 0; }
        .serp-add-btn:hover { border-color: #3b82f6; color: #3b82f6; }
        .serp-paa-item { font-size: 13px; color: #cbd5e1; padding: 6px 10px; border-radius: 6px; background: #0f172a; margin-bottom: 6px; }
        .serp-related { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
        .serp-related-chip { font-size: 12px; padding: 4px 10px; border-radius: 20px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; cursor: pointer; }
        .serp-related-chip:hover { border-color: #3b82f6; color: #93c5fd; }
        .serp-section-label { font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin: 14px 0 8px; }

        /* AI Overview card */
        .ai-overview-card {
            background: linear-gradient(135deg, #0a1628, #111827);
            border: 1px solid #1e40af; border-left: 4px solid #3b82f6;
            border-radius: 12px; padding: 20px; margin-bottom: 16px;
        }
        .ai-overview-label {
            display: flex; align-items: center; gap: 8px;
            font-size: 12px; font-weight: 700; color: #60a5fa;
            text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
        }
        .ai-overview-label::before { content: "✦"; font-size: 14px; }
        .ai-overview-text { font-size: 14px; color: #cbd5e1; line-height: 1.75; margin-bottom: 14px; }
        .ai-overview-section { margin-bottom: 12px; }
        .ai-overview-section-title { font-size: 12px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
        .ai-overview-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .ai-overview-chip { font-size: 12px; padding: 4px 10px; border-radius: 20px; background: #1e293b; color: #cbd5e1; border: 1px solid #334155; }
        .ai-overview-chip.gap { background: #1c0a0a; border-color: #7f1d1d; color: #fca5a5; }
        .ai-overview-chip.question { background: #0a1628; border-color: #1e40af; color: #93c5fd; }
        .ai-overview-reco { font-size: 13px; color: #4ade80; line-height: 1.6; padding: 10px 14px; background: #052e16; border-radius: 8px; border-left: 3px solid #059669; }

        /* Competitor content */
        .comp-content-toggle { font-size: 11px; padding: 3px 8px; margin-top: 10px; border-radius: 5px; border: 1px solid #334155; background: none; color: #64748b; cursor: pointer; width: 100%; }
        .comp-content-toggle:hover { border-color: #3b82f6; color: #93c5fd; }
        .comp-content-body { margin-top: 8px; max-height: 300px; overflow-y: auto; font-size: 11px; color: #94a3b8; line-height: 1.6; white-space: pre-wrap; background: #0a0f1a; padding: 10px; border-radius: 6px; border: 1px solid #1e293b; display: none; }

        /* Verification inline */
        .verify-summary { display: flex; gap: 10px; margin-bottom: 12px; }
        .verify-count { padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; }

        @media (max-width: 768px) {
            .compare-grid { grid-template-columns: 1fr; }
            .step-wizard { flex-wrap: wrap; }
            .step-indicator { flex-basis: 30%; }
            .specialist-cards { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Blog Extractor</h1>
        <p class="subtitle">Extract Contify blog content into clean DOCX documents</p>

        <div class="tabs">
            <button class="tab active" onclick="switchTab('extract')">Extract to DOCX</button>
            <button class="tab" onclick="switchTab('audit')">Check Outdated Info</button>
            <button class="tab" onclick="switchTab('seo')">SEO Content Audit</button>
        </div>

        <!-- Tab 1: Extract -->
        <div class="tab-content active" id="tab-extract">
            <div class="input-group">
                <textarea id="urls" placeholder="Paste blog URLs here (one per line)&#10;&#10;https://www.contify.com/resources/blog/best-competitive-intelligence-tools/"></textarea>
            </div>
            <p class="hint">Supports bulk extraction -- paste multiple URLs, one per line</p>
            <label style="display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;color:#94a3b8;font-size:14px;cursor:pointer;">
                <input type="checkbox" id="includeImages" style="accent-color:#3b82f6;width:16px;height:16px;">
                Include images (slower -- downloads each image)
            </label>
            <br>
            <button class="btn btn-primary" id="extractBtn" onclick="extract()">
                Extract to DOCX
            </button>
            <div class="status" id="status"></div>
            <div class="results" id="results"></div>
            <button class="btn-download-all" id="downloadAllBtn" onclick="downloadAll()">
                Download All (.zip)
            </button>
        </div>

        <!-- Tab 2: AI Audit -->
        <div class="tab-content" id="tab-audit">
            <div class="api-key-section">
                <label class="field-label">Groq API Key (Free)</label>
                <input type="password" id="apiKey" placeholder="gsk_..." value="">
                <div class="api-key-saved" id="apiKeySaved">Key saved for this session</div>
                <p class="powered-by">Powered by Llama 3.3 70B via Groq (free) -- get your key at <a href="https://console.groq.com/keys" target="_blank" style="color:#3b82f6">console.groq.com/keys</a></p>
            </div>
            <div class="input-group">
                <textarea id="auditUrls" placeholder="Paste blog URLs to check for outdated info (one per line)&#10;&#10;https://www.contify.com/resources/blog/best-competitive-intelligence-tools/"></textarea>
            </div>
            <p class="hint">AI reads the full blog content and cross-checks every fact, statistic, pricing, rating, and company info for accuracy</p>
            <button class="btn btn-orange" id="auditBtn" onclick="runAudit()">
                Check Outdated Info
            </button>
            <div class="status" id="auditStatus"></div>
            <div class="audit-report" id="auditReport"></div>
        </div>

        <!-- Tab 3: SEO Content Audit -->
        <div class="tab-content" id="tab-seo">
            <div class="seo-container">

                <!-- Audit History -->
                <div class="audit-history" id="auditHistory" style="display:none">
                    <div class="card-title" style="margin-bottom:12px">Previous Audits</div>
                    <div id="auditHistoryList"></div>
                </div>

                <!-- Step Wizard -->
                <div class="step-wizard">
                    <div class="step-indicator active" onclick="goToStep(1)">1. Input & Keywords</div>
                    <div class="step-indicator" onclick="goToStep(2)">2. Competitors</div>
                    <div class="step-indicator" onclick="goToStep(3)">3. AI Recommendation</div>
                    <div class="step-indicator" onclick="goToStep(4)">4. Edit Framework</div>
                    <div class="step-indicator" onclick="goToStep(5)">5. Final Plan</div>
                </div>

                <!-- Step 1: Input & Keywords -->
                <div class="step-content active" id="step-1">
                    <div class="card">
                        <div class="card-title">Blog URL</div>
                        <input type="text" id="seoUrl" placeholder="https://www.contify.com/resources/blog/...">
                        <br><br>
                        <button class="btn btn-primary" onclick="analyzeBlog()">Analyze Blog</button>
                        <div class="status" id="seoStep1Status"></div>
                    </div>

                    <div class="card" id="step1Results" style="display:none">
                        <div class="card-title">Current Blog Structure</div>
                        <div id="currentTitle" style="font-size:16px;font-weight:700;color:#f8fafc;margin-bottom:12px"></div>
                        <div id="currentHeadings"></div>
                    </div>

                    <!-- Content Verification -->
                    <div class="card" id="step1Verification" style="display:none">
                        <div class="card-title">Content Verification</div>
                        <div class="api-key-section">
                            <label class="field-label">Groq API Key (for AI verification)</label>
                            <input type="password" id="verifyApiKey" placeholder="gsk_...">
                        </div>
                        <button class="btn btn-sm btn-orange" onclick="verifyContent()">Verify Content Accuracy</button>
                        <div class="status" id="verifyStatus"></div>
                        <div id="verifyResults" style="margin-top:16px"></div>
                    </div>

                    <div class="card" id="step1Keywords" style="display:none">
                        <div class="card-title">Target Keyword</div>
                        <input type="text" id="targetKeyword" placeholder="Enter your primary target keyword">
                        <br><br>

                        <!-- Auto Keyword Research -->
                        <div style="background:#0a0f1a;border:1px solid #334155;border-radius:10px;padding:16px;margin-bottom:16px">
                            <div style="font-size:13px;font-weight:700;color:#f8fafc;margin-bottom:4px">Auto Keyword Research <span style="font-size:11px;font-weight:400;color:#64748b">— Ahrefs + SEMrush + SERP in one click</span></div>
                            <p style="font-size:12px;color:#64748b;margin-bottom:12px">Enter keyword above then click research. Fetches related keywords, volumes, KD, CPC and searches top Google results for AI overview, PAA &amp; related searches.</p>
                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
                                <div>
                                    <label class="field-label">Ahrefs API Key</label>
                                    <input type="password" id="ahrefsKey" placeholder="Bearer token from ahrefs.com/api">
                                </div>
                                <div>
                                    <label class="field-label">SEMrush API Key</label>
                                    <input type="password" id="semrushKey" placeholder="API key from semrush.com">
                                </div>
                                <div>
                                    <label class="field-label">SerpAPI Key <span style="font-weight:400;color:#475569">(optional)</span></label>
                                    <input type="text" id="kwSerpKey" placeholder="For Google SERP data">
                                </div>
                                <div>
                                    <label class="field-label">Country / Database</label>
                                    <input type="text" id="kwCountry" placeholder="us" value="us" style="max-width:100px">
                                </div>
                            </div>
                            <button class="btn btn-primary" onclick="runKeywordResearch()">Research Keyword</button>
                            <div class="status" id="kwResearchStatus"></div>
                            <div id="kwResearchResults" style="display:none;margin-top:16px"></div>
                        </div>

                        <div class="card-title">Keyword Data <span style="font-size:11px;font-weight:400;color:#64748b">(auto-filled by research, or paste manually)</span></div>
                        <textarea id="keywordData" placeholder="Paste keyword data here. Format:&#10;keyword | volume | difficulty | cpc&#10;&#10;Example:&#10;competitive intelligence tools | 2400 | 65 | 4.50&#10;best CI tools | 880 | 45 | 3.20&#10;&#10;Also auto-filled when you click Research Keyword above." style="min-height:120px"></textarea>
                        <p class="hint">Supports: pipe-separated, tab-separated, or Semrush CSV export</p>
                        <br>
                        <div class="card-title">People Also Ask Questions</div>
                        <textarea id="paaData" placeholder="Paste PAA questions (one per line) — auto-filled by research&#10;&#10;What is competitive intelligence?&#10;What are the best CI tools?" style="min-height:80px"></textarea>
                        <p class="hint">Auto-filled from SERP research or paste manually. Used by AI for content section recommendations.</p>
                        <br>
                        <button class="btn btn-green" onclick="saveKeywords()">Save Keywords & Continue</button>
                        <div class="status" id="seoKeywordStatus"></div>
                    </div>
                </div>

                <!-- Step 2: Competitor Analysis -->
                <div class="step-content" id="step-2">

                    <!-- SERP Research -->
                    <div class="card">
                        <div class="card-title">SERP Research</div>
                        <p style="font-size:13px;color:#64748b;margin-bottom:14px">Search any keyword and see real Google results. Add a SerpAPI key to unlock AI Overview, PAA, and location/language targeting.</p>

                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
                            <div>
                                <label class="field-label">Keyword</label>
                                <input type="text" id="serpKeyword" placeholder="e.g. competitive intelligence tools">
                            </div>
                            <div>
                                <label class="field-label">Location (optional)</label>
                                <input type="text" id="serpLocation" placeholder="e.g. Gurgaon, Haryana, India">
                            </div>
                            <div>
                                <label class="field-label">Language (hl)</label>
                                <input type="text" id="serpHl" placeholder="en" value="en" style="max-width:120px">
                            </div>
                            <div>
                                <label class="field-label">Country (gl)</label>
                                <input type="text" id="serpGl" placeholder="us" value="us" style="max-width:120px">
                            </div>
                            <div style="grid-column:1/-1">
                                <label class="field-label">Google Domain</label>
                                <input type="text" id="serpDomain" placeholder="google.com" value="google.com" style="max-width:220px">
                            </div>
                        </div>

                        <div style="margin-bottom:12px">
                            <label class="field-label">SerpAPI Key <span style="font-weight:400;color:#475569">(optional — enables Google results + AI Overview)</span></label>
                            <input type="text" id="serpResearchKey" placeholder="Paste your SerpAPI key from serpapi.com">
                            <p style="font-size:11px;color:#475569;margin-top:4px">Without key: uses DuckDuckGo (free, no location targeting). With key: uses real Google results via SerpAPI.</p>
                        </div>

                        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">
                            <button class="btn btn-primary" onclick="researchSerp()">Search &amp; Preview</button>
                            <button class="btn btn-orange" onclick="serpAnalyzeAll()">Search, Read All &amp; Set as Competitors</button>
                        </div>
                        <p style="font-size:11px;color:#475569;margin-bottom:4px">"Read All" scrapes full content from top results and saves them as competitors automatically.</p>

                        <div class="status" id="serpResearchStatus"></div>
                        <div id="serpResults" style="margin-top:16px"></div>
                    </div>

                    <!-- AI Overview (Groq-powered) -->
                    <div class="card" id="aiOverviewCard" style="display:none">
                        <div class="card-title">AI Overview <span style="font-size:12px;font-weight:400;color:#64748b">— Groq synthesizes what top results cover</span></div>
                        <div id="aiOverviewContent"></div>
                    </div>

                    <div class="card">
                        <div class="card-title">Competitor URLs</div>
                        <textarea id="competitorUrls" placeholder="Paste up to 6 competitor URLs (one per line)&#10;&#10;https://competitor1.com/blog/...&#10;https://competitor2.com/blog/..." style="min-height:140px"></textarea>
                        <p class="hint">Paste URLs of pages ranking for your target keyword</p>

                        <div style="margin: 16px 0;">
                            <button class="btn btn-sm btn-ghost" onclick="autoDiscoverCompetitors()">Auto-discover from SERP (uses target keyword)</button>
                            <p style="font-size:11px;color:#475569;margin-top:6px">Searches DuckDuckGo for your target keyword and fills the URLs above automatically.</p>
                        </div>

                        <button class="btn btn-primary" onclick="extractCompetitorHeadings()">Extract Competitor Headings</button>
                        <div class="status" id="seoStep2Status"></div>
                    </div>

                    <div class="card" id="headingGridCard" style="display:none">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px">
                            <div class="card-title" style="margin-bottom:0">Heading Structure Comparison</div>
                            <button class="btn btn-sm btn-primary" onclick="generateAiOverview()">Generate AI Overview of Competitor Content</button>
                        </div>
                        <div class="heading-grid" id="headingGrid"></div>
                    </div>

                    <!-- Gap Analysis Matrix -->
                    <div class="card" id="gapAnalysisCard" style="display:none">
                        <div class="card-title">Topic Gap Analysis</div>
                        <div class="verify-summary" id="gapSummary"></div>
                        <div style="overflow-x:auto">
                            <table class="gap-matrix" id="gapMatrix"></table>
                        </div>
                    </div>
                </div>

                <!-- Step 3: AI Recommendation -->
                <div class="step-content" id="step-3">
                    <div class="card">
                        <div class="card-title">Generate AI-Recommended Structure</div>
                        <div class="api-key-section">
                            <label class="field-label">Groq API Key</label>
                            <input type="password" id="seoApiKey" placeholder="gsk_...">
                            <p class="powered-by">Uses same Groq key as the Audit tab</p>
                        </div>
                        <button class="btn btn-orange" onclick="generateRecommendation()">Generate Recommended Structure</button>
                        <div class="status" id="seoStep3Status"></div>
                    </div>

                    <!-- Specialist Insights -->
                    <div id="specialistInsights" style="display:none" class="card">
                        <div class="card-title">Specialist Analysis</div>
                        <p id="recSummaryText" style="font-size:14px;color:#cbd5e1;line-height:1.6;margin-bottom:16px"></p>
                        <div class="specialist-cards" id="specialistCards"></div>
                        <div id="paaQuestions" style="margin-top:16px;display:none">
                            <div style="font-size:13px;font-weight:700;color:#94a3b8;margin-bottom:8px">People Also Ask (to address in content)</div>
                            <ul id="paaList" style="list-style:disc;padding-left:20px"></ul>
                        </div>
                    </div>

                    <!-- Diff View -->
                    <div id="recDiffView" style="display:none" class="card">
                        <div class="card-title">Recommended Changes</div>
                        <div class="verify-summary" id="diffSummary"></div>
                        <div id="diffList"></div>
                    </div>
                </div>

                <!-- Step 4: Edit Framework -->
                <div class="step-content" id="step-4">
                    <div class="card">
                        <div class="card-title">Edit Content Framework</div>
                        <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap">
                            <button class="btn btn-sm btn-primary" onclick="addHeadingItem()">+ Add Heading</button>
                            <button class="btn btn-sm btn-ghost" onclick="resetToRecommendations()">Reset to AI Recommendations</button>
                            <button class="btn btn-sm btn-green" onclick="saveEdits()">Save Changes</button>
                        </div>
                        <div id="editableList"></div>
                        <div class="status" id="seoStep4Status"></div>
                    </div>

                    <div class="card" id="guidelinesCard">
                        <div class="card-title">Content Guidelines</div>
                        <div id="guidelinesList"></div>
                        <div style="margin-top:16px;padding-top:16px;border-top:1px solid #334155">
                            <input type="text" id="guidelineTitle" placeholder="Guideline title" style="margin-bottom:8px">
                            <textarea id="guidelineContent" placeholder="Guideline content/rules..." style="min-height:60px;margin-bottom:8px"></textarea>
                            <select id="guidelineCategory" style="width:auto;margin-bottom:8px">
                                <option value="general">General</option>
                                <option value="brand_voice">Brand Voice</option>
                                <option value="seo">SEO</option>
                                <option value="structure">Structure</option>
                            </select>
                            <button class="btn btn-sm btn-green" onclick="addGuideline()">Add Guideline</button>
                        </div>
                    </div>
                </div>

                <!-- Step 5: Final Plan -->
                <div class="step-content" id="step-5">
                    <div class="card">
                        <div class="card-title">Generate Final Content Plan</div>
                        <button class="btn btn-primary" onclick="generatePlan()">Generate Final Plan</button>
                        <button class="btn btn-green" onclick="exportPlanDocx()" style="margin-left:10px">Export as DOCX</button>
                        <div class="status" id="seoStep5Status"></div>
                    </div>
                    <div id="planDisplay" style="display:none"></div>
                </div>

            </div>
        </div>
    </div>

    <script>
        let extractedFiles = [];
        let currentAuditId = null;
        let currentStep = 1;
        let currentRecommendations = [];

        // Load saved API keys
        const savedKey = localStorage.getItem('groq_api_key');
        if (savedKey) {
            document.getElementById('apiKey').value = savedKey;
            document.getElementById('seoApiKey').value = savedKey;
        }
        const savedSerpKey = localStorage.getItem('serp_api_key');
        if (savedSerpKey) document.getElementById('serpApiKey').value = savedSerpKey;
        const savedAhrefsKey = localStorage.getItem('ahrefs_api_key');
        if (savedAhrefsKey) document.getElementById('ahrefsKey').value = savedAhrefsKey;
        const savedSemrushKey = localStorage.getItem('semrush_api_key');
        if (savedSemrushKey) document.getElementById('semrushKey').value = savedSemrushKey;

        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            document.querySelector('.tab[onclick*="\\'' + tab + '\\'"]').classList.add('active');
            if (tab === 'seo') loadAuditHistory();
        }

        function goToStep(n) {
            if (!currentAuditId && n > 1) return;
            document.querySelectorAll('.step-content').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.step-indicator').forEach(s => { s.classList.remove('active'); });
            document.getElementById('step-' + n).classList.add('active');
            document.querySelectorAll('.step-indicator')[n-1].classList.add('active');
            for (let i = 0; i < n - 1; i++) {
                document.querySelectorAll('.step-indicator')[i].classList.add('completed');
            }
            currentStep = n;
            if (n === 2) {
                const kw = document.getElementById('targetKeyword').value.trim();
                if (kw) document.getElementById('serpKeyword').value = kw;
                const serpKey = localStorage.getItem('serp_api_key') || '';
                if (serpKey) document.getElementById('serpResearchKey').value = serpKey;
                // Restore last-used targeting settings
                const loc = localStorage.getItem('serp_location');
                const hl = localStorage.getItem('serp_hl');
                const gl = localStorage.getItem('serp_gl');
                const dom = localStorage.getItem('serp_domain');
                if (loc) document.getElementById('serpLocation').value = loc;
                if (hl) document.getElementById('serpHl').value = hl;
                if (gl) document.getElementById('serpGl').value = gl;
                if (dom) document.getElementById('serpDomain').value = dom;
            }
            if (n === 4) { loadEditableList(); loadGuidelines(); }
        }

        // ===================== Tab 1: Extract =====================
        async function extract() {
            const textarea = document.getElementById('urls');
            const btn = document.getElementById('extractBtn');
            const status = document.getElementById('status');
            const results = document.getElementById('results');
            const downloadAllBtn = document.getElementById('downloadAllBtn');
            const urls = textarea.value.trim().split('\\n').map(u => u.trim()).filter(u => u && u.startsWith('http'));
            if (!urls.length) { alert('Please enter at least one URL'); return; }
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Extracting...';
            status.className = 'status loading';
            status.textContent = 'Processing ' + urls.length + ' URL(s)...';
            results.innerHTML = '';
            extractedFiles = [];
            downloadAllBtn.style.display = 'none';
            for (let i = 0; i < urls.length; i++) {
                status.textContent = 'Processing ' + (i + 1) + '/' + urls.length + ': ' + urls[i].substring(0, 60) + '...';
                try {
                    const resp = await fetch('/extract', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: urls[i], includeImages: document.getElementById('includeImages').checked })
                    });
                    const data = await resp.json();
                    if (data.success) {
                        extractedFiles.push(data.filename);
                        results.innerHTML += '<div class="result-item"><span class="result-title">' + escapeHtml(data.title) + '</span><a href="/download/' + data.filename + '" class="btn btn-download">Download</a></div>';
                    } else {
                        results.innerHTML += '<div class="result-item" style="border-color:#7f1d1d"><span class="result-title" style="color:#f87171">' + escapeHtml(urls[i]) + ' -- ' + escapeHtml(data.error) + '</span></div>';
                    }
                } catch (e) {
                    results.innerHTML += '<div class="result-item" style="border-color:#7f1d1d"><span class="result-title" style="color:#f87171">' + escapeHtml(urls[i]) + ' -- ' + escapeHtml(e.message) + '</span></div>';
                }
            }
            status.className = 'status success';
            status.textContent = 'Done! ' + extractedFiles.length + '/' + urls.length + ' extracted successfully.';
            btn.disabled = false;
            btn.innerHTML = 'Extract to DOCX';
            if (extractedFiles.length > 1) downloadAllBtn.style.display = 'block';
        }

        function downloadAll() {
            if (!extractedFiles.length) return;
            const params = extractedFiles.map(f => 'files=' + encodeURIComponent(f)).join('&');
            window.location.href = '/download-all?' + params;
        }

        // ===================== Tab 2: AI Audit =====================
        async function runAudit() {
            const textarea = document.getElementById('auditUrls');
            const btn = document.getElementById('auditBtn');
            const status = document.getElementById('auditStatus');
            const report = document.getElementById('auditReport');
            const apiKey = document.getElementById('apiKey').value.trim();
            if (!apiKey) { alert('Please enter your Groq API key'); return; }
            localStorage.setItem('groq_api_key', apiKey);
            document.getElementById('apiKeySaved').style.display = 'block';
            const urls = textarea.value.trim().split('\\n').map(u => u.trim()).filter(u => u && u.startsWith('http'));
            if (!urls.length) { alert('Please enter at least one URL'); return; }
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> AI is analyzing...';
            status.className = 'status loading';
            status.textContent = 'AI is reading and cross-checking ' + urls.length + ' blog(s)...';
            report.innerHTML = '';
            let allResults = [];
            let totalHigh = 0, totalMedium = 0, totalLow = 0, totalIssues = 0;
            for (let i = 0; i < urls.length; i++) {
                status.textContent = 'AI analyzing ' + (i + 1) + '/' + urls.length + ': ' + urls[i].substring(0, 55) + '...';
                try {
                    const resp = await fetch('/audit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: urls[i], apiKey: apiKey }) });
                    const data = await resp.json();
                    if (data.success) { allResults.push(data.result); totalHigh += data.result.high; totalMedium += data.result.medium; totalLow += data.result.low; totalIssues += data.result.total_issues; }
                    else { allResults.push({ url: urls[i], error: data.error, total_issues: 0, findings: [] }); }
                } catch (e) { allResults.push({ url: urls[i], error: e.message, total_issues: 0, findings: [] }); }
            }
            let html = '<div class="summary-bar"><div class="summary-stat"><div class="num num-total">' + totalIssues + '</div><div class="label">Total Issues</div></div><div class="summary-stat"><div class="num num-high">' + totalHigh + '</div><div class="label">High</div></div><div class="summary-stat"><div class="num num-medium">' + totalMedium + '</div><div class="label">Medium</div></div><div class="summary-stat"><div class="num num-low">' + totalLow + '</div><div class="label">Low</div></div></div>';
            for (const result of allResults) {
                const shortUrl = result.url.replace('https://www.contify.com/resources/blog/', '').replace(/\\/$/, '');
                if (result.error) { html += '<div class="audit-url-block"><div class="audit-url-header"><span class="audit-url-title" style="color:#f87171">' + escapeHtml(shortUrl) + ' -- ' + escapeHtml(result.error) + '</span></div></div>'; continue; }
                const badges = result.total_issues === 0 ? '<span class="badge badge-clean">All Clear</span>' : [result.high > 0 ? '<span class="badge badge-high">' + result.high + ' High</span>' : '', result.medium > 0 ? '<span class="badge badge-medium">' + result.medium + ' Medium</span>' : '', result.low > 0 ? '<span class="badge badge-low">' + result.low + ' Low</span>' : ''].filter(Boolean).join('');
                let findingsHtml = '';
                if (result.findings && result.findings.length > 0) {
                    for (const f of result.findings) {
                        findingsHtml += '<div class="finding-item ' + f.severity + '"><span class="finding-type ' + f.severity + '">' + escapeHtml(f.type) + ' &middot; ' + f.severity + '</span><div class="finding-match">' + escapeHtml(f.match) + '</div>' + (f.context ? '<div class="finding-context">' + escapeHtml(f.context) + '</div>' : '') + (f.issue ? '<div class="finding-issue">' + escapeHtml(f.issue) + '</div>' : '') + (f.suggestion ? '<div class="finding-suggestion">' + escapeHtml(f.suggestion) + '</div>' : '') + '</div>';
                    }
                }
                const blockId = 'block-' + Math.random().toString(36).substr(2, 9);
                html += '<div class="audit-url-block"><div class="audit-url-header" onclick="toggleBlock(\\'' + blockId + '\\')"><span class="audit-url-title">' + escapeHtml(shortUrl) + '</span><div class="audit-badges">' + badges + '</div></div><div class="audit-findings" id="' + blockId + '" style="' + (result.findings.length > 0 ? '' : 'display:none') + '">' + findingsHtml + '</div></div>';
            }
            report.innerHTML = html;
            status.className = 'status success';
            status.textContent = 'Done! Found ' + totalIssues + ' potential issues.';
            btn.disabled = false;
            btn.innerHTML = 'Check Outdated Info';
        }

        function toggleBlock(id) { const el = document.getElementById(id); el.style.display = el.style.display === 'none' ? 'block' : 'none'; }

        // ===================== Tab 3: SEO Content Audit =====================

        // --- Step 1: Analyze Blog ---
        async function analyzeBlog() {
            const url = document.getElementById('seoUrl').value.trim();
            if (!url) { alert('Please enter a blog URL'); return; }
            const status = document.getElementById('seoStep1Status');
            status.className = 'status loading';
            status.textContent = 'Fetching and analyzing blog...';
            try {
                const resp = await fetch('/seo-audit/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url }) });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                currentAuditId = data.audit_id;
                document.getElementById('currentTitle').textContent = data.title;
                let hHtml = '';
                for (const h of data.headings) {
                    hHtml += '<div class="h-item h' + h.level + '"><span class="h-level">' + hLabel(h.level) + '</span> ' + escapeHtml(h.text) + '</div>';
                }
                document.getElementById('currentHeadings').innerHTML = hHtml;
                document.getElementById('step1Results').style.display = 'block';
                document.getElementById('step1Keywords').style.display = 'block';
                document.getElementById('step1Verification').style.display = 'block';
                document.getElementById('targetKeyword').value = data.title.split(/[:|\\-]/)[0].trim().toLowerCase();
                // Sync API keys
                const savedGroqKey = localStorage.getItem('groq_api_key');
                if (savedGroqKey) document.getElementById('verifyApiKey').value = savedGroqKey;
                status.className = 'status success';
                status.textContent = 'Blog analyzed! Found ' + data.headings.length + ' headings.';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        // Content Verification
        async function verifyContent() {
            if (!currentAuditId) return;
            const apiKey = document.getElementById('verifyApiKey').value.trim();
            if (!apiKey) { alert('Please enter your Groq API key'); return; }
            localStorage.setItem('groq_api_key', apiKey);
            const status = document.getElementById('verifyStatus');
            status.className = 'status loading';
            status.textContent = 'AI is verifying content accuracy (checking facts, pricing, features, stats)...';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/verify', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderVerifyResults(data.result);
                status.className = 'status success';
                status.textContent = 'Verification complete! Found ' + data.result.total_issues + ' issues.';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderVerifyResults(result) {
            const el = document.getElementById('verifyResults');
            if (!result.findings || result.findings.length === 0) {
                el.innerHTML = '<div style="color:#4ade80;font-size:14px">No outdated content found.</div>';
                return;
            }
            let html = '<div class="verify-summary">';
            if (result.high > 0) html += '<span class="verify-count badge-high">' + result.high + ' High</span>';
            if (result.medium > 0) html += '<span class="verify-count badge-medium">' + result.medium + ' Medium</span>';
            if (result.low > 0) html += '<span class="verify-count badge-low">' + result.low + ' Low</span>';
            html += '</div>';
            for (const f of result.findings.slice(0, 10)) {
                html += '<div class="finding-item ' + f.severity + '" style="margin-bottom:10px"><span class="finding-type ' + f.severity + '">' + escapeHtml(f.type) + '</span><div class="finding-match">' + escapeHtml(f.match) + '</div>' + (f.issue ? '<div class="finding-issue">' + escapeHtml(f.issue) + '</div>' : '') + (f.suggestion ? '<div class="finding-suggestion">' + escapeHtml(f.suggestion) + '</div>' : '') + '</div>';
            }
            if (result.findings.length > 10) html += '<div style="color:#64748b;font-size:12px;margin-top:8px">+ ' + (result.findings.length - 10) + ' more issues</div>';
            el.innerHTML = html;
        }

        async function saveKeywords() {
            if (!currentAuditId) return;
            const keyword = document.getElementById('targetKeyword').value.trim();
            const kwData = document.getElementById('keywordData').value.trim();
            const paaData = document.getElementById('paaData').value.trim();
            const status = document.getElementById('seoKeywordStatus');
            status.className = 'status loading';
            status.textContent = 'Saving keywords...';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/keywords', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_keyword: keyword, keyword_data: kwData, paa_data: paaData })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                status.className = 'status success';
                status.textContent = 'Saved ' + data.count + ' keywords. Proceed to Step 2.';
                goToStep(2);
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        // --- Keyword Research ---
        async function runKeywordResearch() {
            if (!currentAuditId) { alert('Please analyze a blog URL first (Step 1 — Analyze Blog)'); return; }
            const keyword = document.getElementById('targetKeyword').value.trim();
            if (!keyword) { alert('Enter a target keyword first'); return; }
            const ahrefsKey = document.getElementById('ahrefsKey').value.trim();
            const semrushKey = document.getElementById('semrushKey').value.trim();
            const kwSerpKey = document.getElementById('kwSerpKey').value.trim();
            const country = document.getElementById('kwCountry').value.trim() || 'us';

            // Save keys to localStorage
            if (ahrefsKey) localStorage.setItem('ahrefs_api_key', ahrefsKey);
            if (semrushKey) localStorage.setItem('semrush_api_key', semrushKey);

            const status = document.getElementById('kwResearchStatus');
            status.className = 'status loading';
            status.textContent = 'Researching "' + keyword + '" — fetching Ahrefs, SEMrush & SERP data...';

            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/keyword-research', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        keyword: keyword,
                        ahrefs_key: ahrefsKey,
                        semrush_key: semrushKey,
                        serp_api_key: kwSerpKey || localStorage.getItem('serp_api_key') || '',
                        country: country,
                        database: country,
                    })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderKeywordResearchResults(data.result);
                const kc = (data.result.keywords || []).length;
                const ec = Object.keys(data.result.errors || {}).length;
                status.className = 'status success';
                status.textContent = 'Done! Found ' + kc + ' keywords.' + (ec > 0 ? ' (Some sources had errors — see below)' : '') + ' Keyword data auto-filled below.';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderKeywordResearchResults(result) {
            const container = document.getElementById('kwResearchResults');
            container.style.display = 'block';
            let html = '';

            // API errors (non-fatal)
            if (result.errors && Object.keys(result.errors).length > 0) {
                html += '<div style="padding:8px 12px;background:#1a0a0a;border:1px solid #7f1d1d;border-radius:6px;margin-bottom:12px;font-size:11px;color:#f87171">';
                for (const [src, err] of Object.entries(result.errors)) {
                    html += '<div><strong>' + escapeHtml(src) + ':</strong> ' + escapeHtml(err) + '</div>';
                }
                html += '</div>';
            }

            // Keywords table
            if (result.keywords && result.keywords.length > 0) {
                // Auto-fill keyword data textarea
                const lines = result.keywords.map(kw =>
                    kw.keyword + ' | ' + (kw.volume || 0) + ' | ' + (kw.difficulty || 0) + ' | ' + (kw.cpc ? parseFloat(kw.cpc).toFixed(2) : '0.00')
                );
                document.getElementById('keywordData').value = lines.join('\\n');

                html += '<div style="margin-bottom:16px">';
                html += '<div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px">Related Keywords (' + result.keywords.length + ') — auto-filled in field below</div>';
                html += '<div style="overflow-x:auto"><table class="kw-table">';
                html += '<thead><tr><th>Keyword</th><th style="text-align:right">Volume</th><th style="text-align:right">KD</th><th style="text-align:right">CPC</th><th>Source</th></tr></thead><tbody>';
                for (const kw of result.keywords.slice(0, 40)) {
                    const srcClass = kw.source === 'ahrefs' ? 'kw-src-ahrefs' : kw.source === 'semrush' ? 'kw-src-semrush' : 'kw-src-both';
                    const srcLabel = kw.source === 'ahrefs+semrush' ? 'both' : kw.source;
                    const kdColor = kw.difficulty > 70 ? '#f87171' : kw.difficulty > 40 ? '#fbbf24' : '#4ade80';
                    html += '<tr>';
                    html += '<td>' + escapeHtml(kw.keyword) + (kw.type === 'primary' ? '<span class="kw-primary-badge">PRIMARY</span>' : '') + '</td>';
                    html += '<td style="text-align:right">' + (kw.volume || '—') + '</td>';
                    html += '<td style="text-align:right;color:' + kdColor + '">' + (kw.difficulty || '—') + '</td>';
                    html += '<td style="text-align:right">' + (kw.cpc ? '$' + parseFloat(kw.cpc).toFixed(2) : '—') + '</td>';
                    html += '<td><span class="kw-source ' + srcClass + '">' + escapeHtml(srcLabel) + '</span></td>';
                    html += '</tr>';
                }
                html += '</tbody></table></div></div>';
            }

            // SERP results per keyword
            if (result.serp_results && Object.keys(result.serp_results).length > 0) {
                html += '<div style="margin-bottom:16px"><div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px">SERP Analysis — Top Results per Keyword</div>';
                for (const [kw, serpData] of Object.entries(result.serp_results)) {
                    if (serpData.error) { html += '<div style="font-size:11px;color:#f87171;margin-bottom:6px">' + escapeHtml(kw) + ': ' + escapeHtml(serpData.error) + '</div>'; continue; }
                    html += '<div class="serp-kw-block">';
                    html += '<div class="serp-kw-title">🔍 "' + escapeHtml(kw) + '" <span style="font-size:10px;color:#475569;font-weight:400">via ' + escapeHtml(serpData.source || '') + '</span></div>';
                    if (serpData.ai_overview && serpData.ai_overview.text) {
                        html += '<div style="font-size:11px;background:#0f172a;padding:8px;border-radius:5px;border-left:2px solid #3b82f6;margin-bottom:6px;color:#94a3b8"><strong style="color:#60a5fa">AI Overview: </strong>' + escapeHtml(serpData.ai_overview.text.substring(0, 250)) + '...</div>';
                    }
                    if (serpData.results && serpData.results.length) {
                        for (const r of serpData.results.slice(0, 5)) {
                            html += '<div style="font-size:11px;color:#cbd5e1;padding:2px 0">• ' + escapeHtml(r.title || r.url) + '</div>';
                        }
                    }
                    html += '</div>';
                }
                html += '</div>';
            }

            // Related Searches
            if (result.related_searches && result.related_searches.length > 0) {
                html += '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:6px">Related Searches <span style="font-size:10px;font-weight:400;color:#475569">(click to add to keywords)</span></div>';
                html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
                for (const rs of result.related_searches) {
                    html += '<button class="ai-overview-chip" onclick="addRelatedSearch(\`' + rs.replace(/`/g,'') + '\`)">' + escapeHtml(rs) + '</button>';
                }
                html += '</div></div>';
            }

            // PAA
            if (result.paa_questions && result.paa_questions.length > 0) {
                // Auto-fill PAA textarea
                const existing = document.getElementById('paaData').value.trim();
                const newPaa = result.paa_questions.join('\\n');
                document.getElementById('paaData').value = existing ? existing + '\\n' + newPaa : newPaa;

                html += '<div><div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:6px">People Also Ask <span style="font-size:10px;font-weight:400;color:#64748b">(auto-filled in PAA field below)</span></div>';
                html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
                for (const q of result.paa_questions) {
                    html += '<div style="font-size:11px;color:#94a3b8;background:#0a0f1a;padding:4px 10px;border-radius:4px;border:1px solid #1e293b">' + escapeHtml(q) + '</div>';
                }
                html += '</div></div>';
            }

            container.innerHTML = html;
        }

        function addRelatedSearch(term) {
            const el = document.getElementById('keywordData');
            el.value = (el.value.trim() ? el.value.trim() + '\\n' : '') + term + ' | 0 | 0 | 0.00';
        }

        // --- Step 2: Competitors ---
        async function autoDiscoverCompetitors() {
            const keyword = document.getElementById('targetKeyword').value.trim();
            if (!keyword) { alert('Set target keyword in Step 1 first'); return; }
            const apiKey = localStorage.getItem('serp_api_key') || '';
            const status = document.getElementById('seoStep2Status');
            status.className = 'status loading';
            status.textContent = 'Searching Google for "' + keyword + '"...';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/competitors/auto', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                let urlText = data.results.map(r => r.url).join('\\n');
                document.getElementById('competitorUrls').value = urlText;
                status.className = 'status success';
                status.textContent = 'Found ' + data.results.length + ' competitors. Click "Extract Competitor Headings" to continue.';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        async function extractCompetitorHeadings() {
            const urls = document.getElementById('competitorUrls').value.trim().split('\\n').map(u => u.trim()).filter(u => u && u.startsWith('http'));
            if (!urls.length) { alert('Please enter competitor URLs'); return; }
            if (urls.length > 6) { alert('Maximum 6 competitors allowed'); return; }
            const status = document.getElementById('seoStep2Status');
            status.className = 'status loading';
            status.textContent = 'Extracting headings from ' + urls.length + ' competitors...';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/competitors', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls: urls })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderHeadingGrid(data.user_headings, data.competitors);
                document.getElementById('headingGridCard').style.display = 'block';
                // Gap Analysis
                if (data.gap_analysis) {
                    renderGapAnalysis(data.gap_analysis, data.competitors);
                    document.getElementById('gapAnalysisCard').style.display = 'block';
                }
                const gaps = data.gap_analysis ? data.gap_analysis.summary.gaps + data.gap_analysis.summary.must_haves : 0;
                status.className = 'status success';
                status.textContent = 'Extracted headings from ' + data.competitors.length + ' competitors. ' + gaps + ' content gaps found. Proceed to Step 3.';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderGapAnalysis(analysis, competitors) {
            // Summary
            const s = analysis.summary;
            let summaryHtml = '<span class="verify-count" style="background:#7c2d12;color:#fdba74">' + s.must_haves + ' Must-Have</span>';
            summaryHtml += '<span class="verify-count" style="background:#451a03;color:#fde68a">' + s.gaps + ' Gaps</span>';
            summaryHtml += '<span class="verify-count" style="background:#052e16;color:#86efac">' + s.strengths + ' Unique Strengths</span>';
            summaryHtml += '<span class="verify-count" style="background:#1e293b;color:#94a3b8">' + s.common + ' Common</span>';
            document.getElementById('gapSummary').innerHTML = summaryHtml;

            // Matrix table
            const nc = analysis.num_competitors;
            let html = '<thead><tr><th>Topic</th><th>Category</th><th>Your Blog</th>';
            for (let i = 0; i < nc; i++) {
                const label = competitors[i] ? (competitors[i].title || 'Comp ' + (i+1)).substring(0, 20) : 'Comp ' + (i+1);
                html += '<th title="' + escapeHtml(competitors[i] ? competitors[i].url : '') + '">' + escapeHtml(label) + '</th>';
            }
            html += '<th>Freq</th></tr></thead><tbody>';

            for (const t of analysis.topics) {
                const rowCls = t.category === 'must_have' ? 'gap-row-must-have' : t.category === 'gap' ? 'gap-row-gap' : t.category === 'strength' ? 'gap-row-strength' : '';
                html += '<tr class="' + rowCls + '">';
                html += '<td>' + escapeHtml(t.topic) + '</td>';
                html += '<td><span class="gap-category gap-cat-' + t.category + '">' + t.category.replace('_', ' ') + '</span></td>';
                html += '<td><span class="dot ' + (t.user_has ? 'present' : 'absent') + '"></span></td>';
                for (let i = 0; i < nc; i++) {
                    const has = t.competitors_with.includes(i);
                    html += '<td><span class="dot ' + (has ? 'present' : 'absent') + '"></span></td>';
                }
                html += '<td style="font-weight:600;color:' + (t.frequency >= 4 ? '#f59e0b' : '#94a3b8') + '">' + t.frequency + '/' + nc + '</td>';
                html += '</tr>';
            }
            html += '</tbody>';
            document.getElementById('gapMatrix').innerHTML = html;
        }

        function hLabel(level) {
            return level === 6 ? 'B' : 'H' + level;
        }

        function renderHeadingGrid(userHeadings, competitors) {
            const grid = document.getElementById('headingGrid');
            let html = '<div class="heading-column user-col"><div class="col-title user-label">Your Blog</div>';
            for (const h of userHeadings) {
                html += '<div class="h-item h' + h.level + '"><span class="h-level">' + hLabel(h.level) + '</span> ' + escapeHtml(h.text) + '</div>';
            }
            html += '</div>';
            for (let ci = 0; ci < competitors.length; ci++) {
                const comp = competitors[ci];
                const colId = 'comp-content-' + ci;
                html += '<div class="heading-column"><div class="col-title" title="' + escapeHtml(comp.url) + '">' + escapeHtml(comp.title || comp.url.replace(/https?:\\/\\//, '').split('/')[0]) + '</div>';
                if (comp.error) {
                    html += '<div style="color:#f87171;font-size:12px">Error: ' + escapeHtml(comp.error) + '</div>';
                } else {
                    for (const h of comp.headings) {
                        html += '<div class="h-item h' + h.level + '"><span class="h-level">' + hLabel(h.level) + '</span> ' + escapeHtml(h.text) + '</div>';
                    }
                    if (comp.content) {
                        html += '<button class="comp-content-toggle" onclick="toggleCompContent(\\'' + colId + '\\', this)">Show Article Content</button>';
                        html += '<div class="comp-content-body" id="' + colId + '">' + escapeHtml(comp.content) + '</div>';
                    } else {
                        html += '<div style="font-size:11px;color:#475569;margin-top:8px">No article content extracted</div>';
                    }
                }
                html += '</div>';
            }
            grid.innerHTML = html;
        }

        function toggleCompContent(id, btn) {
            const el = document.getElementById(id);
            if (el.style.display === 'block') {
                el.style.display = 'none';
                btn.textContent = 'Show Article Content';
            } else {
                el.style.display = 'block';
                btn.textContent = 'Hide Content';
            }
        }

        // --- SERP helpers ---
        function getSerpLocation() { return (document.getElementById('serpLocation') || {}).value || ''; }
        function getSerpHl() { return (document.getElementById('serpHl') || {}).value || 'en'; }
        function getSerpGl() { return (document.getElementById('serpGl') || {}).value || 'us'; }
        function getSerpDomain() { return (document.getElementById('serpDomain') || {}).value || 'google.com'; }

        // --- SERP Research ---
        async function researchSerp() {
            const keyword = document.getElementById('serpKeyword').value.trim();
            const apiKey = (document.getElementById('serpResearchKey').value.trim()
                || document.getElementById('serpApiKey').value.trim()
                || localStorage.getItem('serp_api_key') || '');
            if (!keyword) { alert('Enter a keyword to research'); return; }
            if (apiKey) { localStorage.setItem('serp_api_key', apiKey); document.getElementById('serpApiKey').value = apiKey; }
            localStorage.setItem('serp_location', getSerpLocation());
            localStorage.setItem('serp_hl', getSerpHl());
            localStorage.setItem('serp_gl', getSerpGl());
            localStorage.setItem('serp_domain', getSerpDomain());
            const status = document.getElementById('serpResearchStatus');
            document.getElementById('serpResults').innerHTML = '';
            status.className = 'status loading';
            const source = apiKey ? 'Google (SerpAPI)' : 'DuckDuckGo (free)';
            status.textContent = 'Searching "' + keyword + '" via ' + source + '...';
            try {
                const serpEndpoint = currentAuditId ? '/seo-audit/' + currentAuditId + '/serp' : '/api/serp';
                const resp = await fetch(serpEndpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        api_key: apiKey, keyword: keyword,
                        location: getSerpLocation(), hl: getSerpHl(),
                        gl: getSerpGl(), google_domain: getSerpDomain()
                    })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderSerpResults(data);
                const usedSource = data.source === 'serpapi' ? 'Google (SerpAPI)' : data.source === 'duckduckgo' ? 'DuckDuckGo' : 'search';
                status.className = 'status success';
                status.textContent = 'Found ' + data.results.length + ' results for "' + keyword + '" via ' + usedSource;
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderSerpResults(data) {
            const el = document.getElementById('serpResults');
            let html = '';

            // AI Overview
            if (data.ai_overview && data.ai_overview.text) {
                html += '<div class="serp-ai-overview">' +
                    '<div class="serp-ai-label">AI Overview (Google AI)</div>' +
                    '<div class="serp-ai-text">' + escapeHtml(data.ai_overview.text) + '</div>';
                if (data.ai_overview.sources && data.ai_overview.sources.length) {
                    html += '<div class="serp-ai-sources">Sources: ' + data.ai_overview.sources.slice(0, 3).map(s => {
                        try { return new URL(s).hostname; } catch { return s; }
                    }).join(', ') + '</div>';
                }
                html += '</div>';
            }

            // Featured Snippet
            if (data.featured_snippet && data.featured_snippet.answer) {
                const fs = data.featured_snippet;
                html += '<div class="serp-featured">' +
                    '<div class="serp-featured-label">Featured Snippet' + (fs.type ? ' · ' + fs.type : '') + '</div>' +
                    (fs.title ? '<div style="font-size:13px;font-weight:600;color:#93c5fd;margin-bottom:4px">' + escapeHtml(fs.title) + '</div>' : '') +
                    '<div style="font-size:13px;color:#cbd5e1;line-height:1.6">' + escapeHtml(fs.answer) + '</div>' +
                    (fs.source ? '<div style="font-size:11px;color:#4ade80;margin-top:6px">' + escapeHtml(fs.source) + '</div>' : '') +
                    '</div>';
            }

            // Organic Results
            if (data.results && data.results.length) {
                html += '<div class="serp-section-label">Organic Results</div>';
                for (const r of data.results) {
                    html += '<div class="serp-result-item">' +
                        '<div class="serp-pos">#' + r.position + '</div>' +
                        '<div class="serp-result-body">' +
                        '<div class="serp-result-title" title="' + escapeHtml(r.url) + '">' + escapeHtml(r.title) + '</div>' +
                        '<div class="serp-result-domain">' + escapeHtml(r.domain || r.url.replace(/https?:\\/\\//, '').split('/')[0]) + '</div>' +
                        (r.snippet ? '<div class="serp-result-snippet">' + escapeHtml(r.snippet) + '</div>' : '') +
                        '</div>' +
                        '<button class="serp-add-btn" onclick="addSerpUrlToCompetitors(\\'' + escapeHtml(r.url) + '\\')">+ Add</button>' +
                        '</div>';
                }
            }

            // PAA Questions
            if (data.paa_questions && data.paa_questions.length) {
                html += '<div class="serp-section-label">People Also Ask</div>';
                for (const q of data.paa_questions) {
                    html += '<div class="serp-paa-item">Q: ' + escapeHtml(q) + ' <button class="serp-add-btn" onclick="addPaaToPaste(\\'' + escapeHtml(q) + '\\')">+ Add to PAA</button></div>';
                }
            }

            // Related Searches
            if (data.related_searches && data.related_searches.length) {
                html += '<div class="serp-section-label">Related Searches</div><div class="serp-related">';
                for (const r of data.related_searches) {
                    html += '<span class="serp-related-chip" onclick="searchRelated(\\'' + escapeHtml(r) + '\\')">' + escapeHtml(r) + '</span>';
                }
                html += '</div>';
            }

            el.innerHTML = html || '<div style="color:#64748b;font-size:13px">No results found.</div>';
        }

        async function serpAnalyzeAll() {
            if (!currentAuditId) { alert('First analyze your blog URL in Step 1'); return; }
            const keyword = document.getElementById('serpKeyword').value.trim()
                || document.getElementById('targetKeyword').value.trim();
            if (!keyword) { alert('Enter a keyword to research'); return; }
            const apiKey = document.getElementById('serpResearchKey').value.trim()
                || localStorage.getItem('serp_api_key') || '';
            const status = document.getElementById('serpResearchStatus');
            status.className = 'status loading';
            status.textContent = 'Searching "' + keyword + '" and reading all top pages... this takes 30-60 seconds.';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/serp-analyze', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        keyword: keyword, api_key: apiKey,
                        location: getSerpLocation(), hl: getSerpHl(),
                        gl: getSerpGl(), google_domain: getSerpDomain()
                    })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);

                // Render heading grid + gap analysis (same as extractCompetitorHeadings)
                renderHeadingGrid(data.user_headings, data.competitors);
                document.getElementById('headingGridCard').style.display = 'block';
                if (data.gap_analysis) {
                    renderGapAnalysis(data.gap_analysis, data.competitors);
                    document.getElementById('gapAnalysisCard').style.display = 'block';
                }
                // Show SERP extras (AI overview etc)
                if (data.ai_overview || data.featured_snippet || data.paa_questions.length) {
                    renderSerpResults(data);
                    document.getElementById('serpResults').scrollIntoView({ behavior: 'smooth' });
                }
                // Pre-fill PAA
                if (data.paa_questions && data.paa_questions.length) {
                    const existing = document.getElementById('paaData').value.trim();
                    const newPaa = data.paa_questions.join('\\n');
                    document.getElementById('paaData').value = existing ? existing + '\\n' + newPaa : newPaa;
                }
                const gaps = data.gap_analysis ? data.gap_analysis.summary.gaps + data.gap_analysis.summary.must_haves : 0;
                status.className = 'status success';
                status.textContent = 'Done! Read ' + data.competitors.length + ' pages. Found ' + gaps + ' content gaps. Generating AI Overview...';
                // Auto-generate AI Overview if Groq key available
                const groqKey = localStorage.getItem('groq_api_key') || '';
                if (groqKey) {
                    generateAiOverview().then(() => {
                        status.textContent = 'Done! Read ' + data.competitors.length + ' pages. Found ' + gaps + ' content gaps. AI Overview ready. Go to Step 3 for recommendations.';
                    });
                } else {
                    status.textContent = 'Done! Read ' + data.competitors.length + ' pages. Found ' + gaps + ' content gaps. Click "Generate AI Overview" above for content synthesis.';
                }
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function addSerpUrlToCompetitors(url) {
            const ta = document.getElementById('competitorUrls');
            const existing = ta.value.trim();
            ta.value = existing ? existing + '\\n' + url : url;
        }

        function addPaaToPaste(question) {
            const ta = document.getElementById('paaData');
            const existing = ta.value.trim();
            ta.value = existing ? existing + '\\n' + question : question;
        }

        function searchRelated(keyword) {
            document.getElementById('serpKeyword').value = keyword;
            researchSerp();
        }

        // --- AI Overview ---
        async function generateAiOverview() {
            if (!currentAuditId) { alert('Extract competitor content first'); return; }
            const apiKey = document.getElementById('seoApiKey').value.trim()
                || document.getElementById('apiKey').value.trim()
                || localStorage.getItem('groq_api_key') || '';
            if (!apiKey) { alert('Enter your Groq API key in Step 3 first, or in the Audit tab'); return; }
            const card = document.getElementById('aiOverviewCard');
            const content = document.getElementById('aiOverviewContent');
            card.style.display = 'block';
            content.innerHTML = '<div class="status loading" style="display:block">Reading all competitor content and generating AI Overview... (30-45 seconds)</div>';
            card.scrollIntoView({ behavior: 'smooth' });
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/ai-overview', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderAiOverview(data.overview);
            } catch (e) {
                content.innerHTML = '<div class="status error" style="display:block">Error: ' + escapeHtml(e.message) + '</div>';
            }
        }

        function renderAiOverview(ov) {
            let html = '<div class="ai-overview-card">';
            html += '<div class="ai-overview-label">AI Overview — synthesized from top ' + (ov.main_topics ? 'ranking' : '') + ' competitor content</div>';

            if (ov.overview) {
                html += '<div class="ai-overview-text">' + escapeHtml(ov.overview).replace(/\n/g, '<br>') + '</div>';
            }

            if (ov.main_topics && ov.main_topics.length) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">Main Topics Covered</div><div class="ai-overview-chips">';
                html += ov.main_topics.map(t => '<span class="ai-overview-chip">' + escapeHtml(t) + '</span>').join('');
                html += '</div></div>';
            }

            if (ov.questions_answered && ov.questions_answered.length) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">Questions Answered by Top Results</div><div class="ai-overview-chips">';
                html += ov.questions_answered.map(q => '<span class="ai-overview-chip question">' + escapeHtml(q) + '</span>').join('');
                html += '</div></div>';
            }

            if (ov.content_patterns) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">Content Pattern</div>';
                html += '<div style="font-size:13px;color:#94a3b8;line-height:1.6">' + escapeHtml(ov.content_patterns) + '</div></div>';
            }

            if (ov.unique_angles && ov.unique_angles.length) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">Unique Angles (in only 1-2 results)</div><div class="ai-overview-chips">';
                html += ov.unique_angles.map(a => '<span class="ai-overview-chip">' + escapeHtml(a) + '</span>').join('');
                html += '</div></div>';
            }

            if (ov.content_gaps && ov.content_gaps.length) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">Content Gaps — Missing from Top Results (Your Opportunity)</div><div class="ai-overview-chips">';
                html += ov.content_gaps.map(g => '<span class="ai-overview-chip gap">' + escapeHtml(g) + '</span>').join('');
                html += '</div></div>';
            }

            if (ov.recommended_approach) {
                html += '<div class="ai-overview-section"><div class="ai-overview-section-title">How to Beat These Results</div>';
                html += '<div class="ai-overview-reco">' + escapeHtml(ov.recommended_approach) + '</div></div>';
            }

            html += '</div>';
            document.getElementById('aiOverviewContent').innerHTML = html;
        }

        // --- Step 3: AI Recommendations ---
        async function generateRecommendation() {
            const apiKey = document.getElementById('seoApiKey').value.trim() || document.getElementById('apiKey').value.trim() || document.getElementById('verifyApiKey').value.trim();
            if (!apiKey) { alert('Please enter your Groq API key'); return; }
            localStorage.setItem('groq_api_key', apiKey);
            document.getElementById('seoApiKey').value = apiKey;
            document.getElementById('apiKey').value = apiKey;
            const status = document.getElementById('seoStep3Status');
            status.className = 'status loading';
            status.textContent = 'Running 3-specialist analysis (Content + PMM + SEO)... This takes 30-45 seconds.';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/recommend', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                currentRecommendations = data.recommendations;

                // Summary + Specialist Insights
                document.getElementById('recSummaryText').textContent = data.summary || '';
                renderSpecialistInsights(data.key_insights, data.specialist_analyses);
                document.getElementById('specialistInsights').style.display = 'block';

                // PAA
                if (data.paa_questions && data.paa_questions.length) {
                    const paaList = document.getElementById('paaList');
                    paaList.innerHTML = data.paa_questions.map(q => '<li style="color:#67e8f9;font-size:13px;margin-bottom:4px">' + escapeHtml(q) + '</li>').join('');
                    document.getElementById('paaQuestions').style.display = 'block';
                }

                // Diff View
                renderDiffView(data.recommendations);
                document.getElementById('recDiffView').style.display = 'block';

                const gaps = data.recommendations.filter(r => r.is_gap || r.diff_status === 'new').length;
                const rewords = data.recommendations.filter(r => r.diff_status === 'reword').length;
                status.className = 'status success';
                status.textContent = '3-specialist analysis complete! ' + gaps + ' content gaps, ' + rewords + ' heading rewrites recommended.';
                if (data.errors && data.errors.length) {
                    status.textContent += ' (Warnings: ' + data.errors.join('; ') + ')';
                }
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderSpecialistInsights(keyInsights, analyses) {
            const cards = document.getElementById('specialistCards');
            let html = '';
            const specs = [
                {key: 'content', label: 'Content Specialist', cls: 'content-spec', icon: 'Information Architecture, Depth & Flow'},
                {key: 'pmm', label: 'PMM Specialist', cls: 'pmm-spec', icon: 'Positioning, Buyer Journey & Differentiation'},
                {key: 'seo', label: 'SEO Specialist', cls: 'seo-spec', icon: 'Keywords, Search Intent & Featured Snippets'},
            ];
            for (const spec of specs) {
                const insight = (keyInsights && keyInsights[spec.key]) || '';
                const analysis = analyses && analyses[spec.key];
                let detailHtml = '';
                if (analysis) {
                    const adds = (analysis.topics_to_add || []).length;
                    const rewords = (analysis.topics_to_reword || []).length;
                    const removes = (analysis.topics_to_remove || []).length;
                    detailHtml = '<div style="margin-top:10px;font-size:11px;color:#64748b">' +
                        (adds > 0 ? '<span style="color:#fdba74">+' + adds + ' add</span> ' : '') +
                        (rewords > 0 ? '<span style="color:#93c5fd">' + rewords + ' reword</span> ' : '') +
                        (removes > 0 ? '<span style="color:#fca5a5">-' + removes + ' remove</span>' : '') +
                        '</div>';
                    // Score
                    const score = analysis.reader_flow_score || analysis.keyword_coverage_score;
                    if (score) detailHtml += '<div style="font-size:11px;color:#64748b;margin-top:4px">Score: ' + score + '/10</div>';
                    // Buyer journey
                    if (analysis.buyer_journey_coverage) {
                        const bj = analysis.buyer_journey_coverage;
                        detailHtml += '<div style="font-size:11px;margin-top:4px">';
                        for (const [stage, status] of Object.entries(bj)) {
                            const color = status === 'good' ? '#4ade80' : status === 'weak' ? '#fde68a' : '#fca5a5';
                            detailHtml += '<span style="color:' + color + '">' + stage + ': ' + status + '</span> ';
                        }
                        detailHtml += '</div>';
                    }
                }
                html += '<div class="specialist-card ' + spec.cls + '">' +
                    '<div class="specialist-label ' + spec.cls + '">' + spec.label + '</div>' +
                    '<div style="font-size:11px;color:#64748b;margin-bottom:8px">' + spec.icon + '</div>' +
                    '<div class="specialist-insight">' + escapeHtml(insight) + '</div>' +
                    detailHtml + '</div>';
            }
            cards.innerHTML = html;
        }

        function renderDiffView(recs) {
            // Summary counts
            const counts = {keep: 0, reword: 0, new: 0, remove: 0};
            for (const r of recs) { counts[r.diff_status || 'new']++; }
            let summaryHtml = '';
            if (counts.keep) summaryHtml += '<span class="verify-count" style="background:#052e16;color:#4ade80">' + counts.keep + ' Keep</span>';
            if (counts.reword) summaryHtml += '<span class="verify-count" style="background:#172554;color:#93c5fd">' + counts.reword + ' Reword</span>';
            if (counts.new) summaryHtml += '<span class="verify-count" style="background:#431407;color:#fdba74">' + counts.new + ' New</span>';
            if (counts.remove) summaryHtml += '<span class="verify-count" style="background:#450a0a;color:#fca5a5">' + counts.remove + ' Remove</span>';
            document.getElementById('diffSummary').innerHTML = summaryHtml;

            // Diff items
            let html = '';
            for (const r of recs) {
                const ds = r.diff_status || 'new';
                const conf = r.confidence || 0;
                const confCls = conf >= 80 ? 'confidence-high' : conf >= 60 ? 'confidence-medium' : 'confidence-low';

                html += '<div class="diff-item diff-' + ds + '">';
                html += '<span class="diff-badge diff-badge-' + ds + '">' + ds.toUpperCase() + '</span>';
                html += '<div style="flex:1">';

                if (ds === 'reword' && r.original_text) {
                    html += '<div><span class="diff-original">' + escapeHtml(r.original_text) + '</span><span class="diff-arrow"> &rarr; </span><span class="h-item h' + r.level + '" style="display:inline"><span class="h-level">H' + r.level + '</span> ' + escapeHtml(r.text) + '</span></div>';
                } else if (ds === 'remove') {
                    html += '<div class="h-item h' + r.level + '" style="text-decoration:line-through;opacity:0.6"><span class="h-level">H' + r.level + '</span> ' + escapeHtml(r.text) + '</div>';
                } else {
                    html += '<div class="h-item h' + r.level + '"><span class="h-level">H' + r.level + '</span> ' + escapeHtml(r.text) + '</div>';
                }
                if (r.is_gap) html += '<span class="badge badge-gap" style="font-size:10px">GAP</span> ';
                if (conf > 0) html += '<span class="confidence-badge ' + confCls + '">' + conf + '% confidence</span>';
                if (r.reason) html += '<div class="rec-reason" style="margin-top:4px">' + escapeHtml(r.reason) + '</div>';
                if (r.specialist_sources && r.specialist_sources.length) {
                    html += '<div style="font-size:10px;color:#475569;margin-top:2px">Sources: ' + r.specialist_sources.join(', ') + '</div>';
                }
                html += '</div></div>';
            }
            document.getElementById('diffList').innerHTML = html;
        }

        // --- Step 4: Edit Framework ---
        async function loadEditableList() {
            if (!currentAuditId) return;
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/recommendations');
                const data = await resp.json();
                if (data.success) {
                    currentRecommendations = data.recommendations;
                    renderEditableList(data.recommendations);
                }
            } catch (e) { console.error(e); }
        }

        function renderEditableList(recs) {
            const list = document.getElementById('editableList');
            let html = '';
            for (let i = 0; i < recs.length; i++) {
                const r = recs[i];
                const statusCls = r.status === 'accepted' ? 'accepted' : r.status === 'rejected' ? 'rejected' : '';
                const gapBadge = r.is_gap ? '<span class="badge badge-gap" style="margin-left:8px;font-size:10px">GAP</span>' : '';
                html += '<div class="edit-item ' + statusCls + '" data-id="' + r.id + '">' +
                    '<select onchange="updateRecLevel(this,' + r.id + ')" style="width:70px">' +
                    [1,2,3,4].map(l => '<option value="' + l + '"' + (r.heading_level === l ? ' selected' : '') + '>H' + l + '</option>').join('') +
                    '</select>' +
                    '<input type="text" value="' + escapeHtml(r.heading_text) + '" onchange="updateRecText(this,' + r.id + ')">' +
                    gapBadge +
                    '<div class="edit-actions">' +
                    '<button class="btn btn-sm ' + (r.status === 'accepted' ? 'btn-green' : 'btn-ghost') + '" onclick="setRecStatus(' + r.id + ',\\'accepted\\')">Accept</button>' +
                    '<button class="btn btn-sm ' + (r.status === 'rejected' ? 'btn-danger' : 'btn-ghost') + '" onclick="setRecStatus(' + r.id + ',\\'rejected\\')">Reject</button>' +
                    '<button class="btn btn-sm btn-danger" onclick="deleteRec(' + r.id + ')" title="Delete">X</button>' +
                    '</div>' +
                    '</div>';
                if (r.change_reason) {
                    html += '<div style="font-size:11px;color:#94a3b8;padding:0 14px 8px 84px;margin-top:-6px">Reason: ' + escapeHtml(r.change_reason) + '</div>';
                }
            }
            list.innerHTML = html || '<p style="color:#64748b">No recommendations yet. Generate them in Step 3 first.</p>';
        }

        async function updateRecLevel(el, recId) {
            await fetch('/seo-audit/' + currentAuditId + '/recommendations', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rec_id: recId, heading_level: parseInt(el.value) })
            });
        }
        async function updateRecText(el, recId) {
            await fetch('/seo-audit/' + currentAuditId + '/recommendations', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rec_id: recId, heading_text: el.value })
            });
        }
        async function setRecStatus(recId, status) {
            await fetch('/seo-audit/' + currentAuditId + '/recommendations', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rec_id: recId, status: status })
            });
            loadEditableList();
        }
        async function deleteRec(recId) {
            await fetch('/seo-audit/' + currentAuditId + '/recommendations', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rec_id: recId, action: 'delete' })
            });
            loadEditableList();
        }
        async function addHeadingItem() {
            if (!currentAuditId) return;
            await fetch('/seo-audit/' + currentAuditId + '/recommendations', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'add', heading_level: 2, heading_text: 'New Section' })
            });
            loadEditableList();
        }
        async function resetToRecommendations() {
            if (!confirm('Reset all edits to AI recommendations?')) return;
            const apiKey = document.getElementById('seoApiKey').value.trim() || document.getElementById('apiKey').value.trim();
            await generateRecommendation();
            loadEditableList();
        }
        async function saveEdits() {
            const status = document.getElementById('seoStep4Status');
            status.className = 'status success';
            status.textContent = 'All changes saved automatically. Proceed to Step 5.';
        }

        // Guidelines
        async function loadGuidelines() {
            try {
                const resp = await fetch('/guidelines');
                const data = await resp.json();
                const list = document.getElementById('guidelinesList');
                if (data.guidelines && data.guidelines.length) {
                    list.innerHTML = data.guidelines.map(g =>
                        '<div class="guideline-item"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div><div class="guideline-title">' + escapeHtml(g.title) + '</div><div class="guideline-content">' + escapeHtml(g.content) + '</div><div class="guideline-cat">' + escapeHtml(g.category) + '</div></div><button class="btn btn-sm btn-danger" onclick="removeGuideline(' + g.id + ')">X</button></div></div>'
                    ).join('');
                } else {
                    list.innerHTML = '<p style="color:#64748b;font-size:13px">No guidelines yet. Add content rules, brand voice notes, or SEO guidelines below.</p>';
                }
            } catch (e) { console.error(e); }
        }
        async function addGuideline() {
            const title = document.getElementById('guidelineTitle').value.trim();
            const content = document.getElementById('guidelineContent').value.trim();
            const category = document.getElementById('guidelineCategory').value;
            if (!title || !content) { alert('Please fill in title and content'); return; }
            await fetch('/guidelines', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, content, category }) });
            document.getElementById('guidelineTitle').value = '';
            document.getElementById('guidelineContent').value = '';
            loadGuidelines();
        }
        async function removeGuideline(id) {
            await fetch('/guidelines/' + id, { method: 'DELETE' });
            loadGuidelines();
        }

        // --- Step 5: Final Plan ---
        async function generatePlan() {
            const apiKey = document.getElementById('seoApiKey').value.trim() || document.getElementById('apiKey').value.trim();
            if (!apiKey) { alert('Please enter your Groq API key'); return; }
            const status = document.getElementById('seoStep5Status');
            status.className = 'status loading';
            status.textContent = 'Generating final content plan...';
            try {
                const resp = await fetch('/seo-audit/' + currentAuditId + '/plan', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });
                const data = await resp.json();
                if (!data.success) throw new Error(data.error);
                renderPlan(data.plan);
                document.getElementById('planDisplay').style.display = 'block';
                status.className = 'status success';
                status.textContent = 'Content plan generated and saved!';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        function renderPlan(plan) {
            let html = '<div class="plan-meta">';
            if (plan.title) html += '<div class="plan-meta-item"><span class="plan-meta-label">Title: </span>' + escapeHtml(plan.title) + '</div>';
            if (plan.target_keyword) html += '<div class="plan-meta-item"><span class="plan-meta-label">Target Keyword: </span>' + escapeHtml(plan.target_keyword) + '</div>';
            if (plan.total_word_count) html += '<div class="plan-meta-item"><span class="plan-meta-label">Total Word Count: </span>' + plan.total_word_count + '</div>';
            if (plan.meta_title) html += '<div class="plan-meta-item"><span class="plan-meta-label">Meta Title: </span>' + escapeHtml(plan.meta_title) + '</div>';
            if (plan.meta_description) html += '<div class="plan-meta-item"><span class="plan-meta-label">Meta Description: </span>' + escapeHtml(plan.meta_description) + '</div>';
            html += '</div>';
            if (plan.sections) {
                for (const sec of plan.sections) {
                    const gapCls = sec.is_gap ? ' gap-section' : '';
                    html += '<div class="plan-section' + gapCls + '">';
                    html += '<div class="plan-heading">' + escapeHtml(sec.heading) + (sec.is_gap ? ' <span class="badge badge-gap">GAP</span>' : '') + '</div>';
                    if (sec.key_points && sec.key_points.length) {
                        html += '<ul class="plan-points">' + sec.key_points.map(p => '<li>' + escapeHtml(p) + '</li>').join('') + '</ul>';
                    }
                    if (sec.keywords_to_include && sec.keywords_to_include.length) {
                        html += '<div class="plan-kw">Keywords: ' + sec.keywords_to_include.map(k => escapeHtml(k)).join(', ') + '</div>';
                    }
                    if (sec.word_count) html += '<div class="plan-wc">~' + sec.word_count + ' words</div>';
                    if (sec.notes) html += '<div style="font-size:12px;color:#94a3b8;margin-top:6px">' + escapeHtml(sec.notes) + '</div>';
                    html += '</div>';
                }
            }
            document.getElementById('planDisplay').innerHTML = html;
        }

        async function exportPlanDocx() {
            if (!currentAuditId) return;
            window.location.href = '/seo-audit/' + currentAuditId + '/export';
        }

        // --- Audit History ---
        async function loadAuditHistory() {
            try {
                const resp = await fetch('/seo-audit/list');
                const data = await resp.json();
                if (data.audits && data.audits.length) {
                    const list = document.getElementById('auditHistoryList');
                    list.innerHTML = data.audits.map(a =>
                        '<div class="audit-history-item" onclick="loadAudit(' + a.id + ')">' +
                        '<div class="audit-history-title">' + escapeHtml(a.blog_title || a.blog_url) + '</div>' +
                        '<div class="audit-history-meta">' + escapeHtml(a.target_keyword || '') + ' | ' + a.status + ' | ' + (a.created_at || '').substring(0, 10) + '</div>' +
                        '</div>'
                    ).join('');
                    document.getElementById('auditHistory').style.display = 'block';
                }
            } catch (e) { console.error(e); }
        }

        async function loadAudit(id) {
            try {
                const resp = await fetch('/seo-audit/' + id);
                const data = await resp.json();
                if (data.success) {
                    currentAuditId = id;
                    document.getElementById('seoUrl').value = data.audit.blog_url;
                    document.getElementById('targetKeyword').value = data.audit.target_keyword || '';
                    if (data.audit.blog_title) {
                        document.getElementById('currentTitle').textContent = data.audit.blog_title;
                        document.getElementById('step1Results').style.display = 'block';
                        document.getElementById('step1Keywords').style.display = 'block';
                    }
                    goToStep(1);
                }
            } catch (e) { console.error(e); }
        }

        function escapeHtml(str) {
            if (!str) return '';
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/extract", methods=["POST"])
def extract():
    data = request.get_json()
    url = data.get("url", "").strip()
    include_images = data.get("includeImages", False)
    if not url:
        return jsonify(success=False, error="No URL provided")
    try:
        html = fetch_page(url)
        soup = parse_html(html)
        title = extract_title(soup)
        content = find_article_content(soup)
        clean_content(content)
        if not include_images:
            for img in content.find_all(["img", "figure"]):
                img.decompose()
        builder = DocxBuilder(url)
        builder.add_heading(title, level=0)
        builder.doc.add_paragraph("")
        process_element(content, builder)
        builder.doc.add_paragraph("")
        source_para = builder.doc.add_paragraph()
        source_para.add_run("Source: ").bold = True
        add_hyperlink(source_para, url, url)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", title)[:80].strip()
        safe_title = re.sub(r"[\s]+", "_", safe_title)
        filename = f"{safe_title}.docx"
        filepath = os.path.join(OUTPUT_DIR, filename)
        builder.save(filepath)
        return jsonify(success=True, title=title, filename=filename)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/audit", methods=["POST"])
def audit():
    data = request.get_json()
    url = data.get("url", "").strip()
    api_key = data.get("apiKey", "").strip()
    if not url:
        return jsonify(success=False, error="No URL provided")
    if not api_key:
        return jsonify(success=False, error="No API key provided")
    try:
        html = fetch_page(url)
        soup = parse_html(html)
        content = find_article_content(soup)
        clean_content(content)
        result = analyze_content(content, url, api_key=api_key)
        if result.get("error"):
            return jsonify(success=False, error=result["error"])
        return jsonify(success=True, result=result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route("/download-all")
def download_all():
    filenames = request.args.getlist("files")
    if not filenames:
        return "No files specified", 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in filenames:
            filepath = os.path.join(OUTPUT_DIR, fname)
            if os.path.exists(filepath):
                zf.write(filepath, fname)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="blog-extracts.zip")


# ===================== SEO Audit Routes =====================

@app.route("/seo-audit/create", methods=["POST"])
def seo_audit_create():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify(success=False, error="No URL provided")
    try:
        result = extract_headings(url)
        audit_id = create_audit(url, result["title"])
        save_headings(audit_id, result["headings"])
        return jsonify(success=True, audit_id=audit_id, title=result["title"], headings=result["headings"])
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/list")
def seo_audit_list():
    audits = list_audits()
    return jsonify(success=True, audits=audits)


@app.route("/seo-audit/<int:audit_id>")
def seo_audit_get(audit_id):
    audit = get_audit(audit_id)
    if not audit:
        return jsonify(success=False, error="Audit not found")
    return jsonify(success=True, audit=audit)


@app.route("/seo-audit/<int:audit_id>/keyword-research", methods=["POST"])
def seo_audit_keyword_research(audit_id):
    """Auto keyword research: Ahrefs + SEMrush + SERP → save to DB."""
    data = request.get_json()
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify(success=False, error="Keyword required")
    try:
        result = run_keyword_research(
            keyword,
            ahrefs_key=data.get("ahrefs_key", "").strip(),
            semrush_key=data.get("semrush_key", "").strip(),
            serp_api_key=data.get("serp_api_key", "").strip(),
            country=data.get("country", "us"),
            database=data.get("database", "us"),
            num_serp_keywords=3,
        )
        # Save keywords + PAA to DB
        keywords_to_save = [{"keyword": keyword, "type": "primary", "volume": None, "difficulty": None, "cpc": None}]
        for kw in result.get("keywords", [])[:50]:
            keywords_to_save.append({
                "keyword": kw["keyword"],
                "volume": kw.get("volume"),
                "difficulty": kw.get("difficulty"),
                "cpc": kw.get("cpc"),
                "type": kw.get("type", "related"),
            })
        for q in result.get("paa_questions", []):
            keywords_to_save.append({"keyword": q, "type": "paa", "volume": None, "difficulty": None, "cpc": None})
        save_keywords(audit_id, keywords_to_save)
        update_audit(audit_id, target_keyword=keyword)
        return jsonify(success=True, result=result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/keywords", methods=["POST"])
def seo_audit_keywords(audit_id):
    data = request.get_json()
    target_kw = data.get("target_keyword", "").strip()
    kw_data = data.get("keyword_data", "").strip()
    paa_data = data.get("paa_data", "").strip()

    if target_kw:
        update_audit(audit_id, target_keyword=target_kw)

    keywords = []
    if target_kw:
        keywords.append({"keyword": target_kw, "type": "primary"})
    if kw_data:
        keywords.extend(parse_keyword_input(kw_data))
    if paa_data:
        keywords.extend(parse_paa_input(paa_data))

    save_keywords(audit_id, keywords)
    return jsonify(success=True, count=len(keywords))


@app.route("/seo-audit/<int:audit_id>/verify", methods=["POST"])
def seo_audit_verify(audit_id):
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify(success=False, error="Groq API key required")

    audit = get_audit(audit_id)
    if not audit:
        return jsonify(success=False, error="Audit not found")

    try:
        html = fetch_page(audit["blog_url"])
        soup = parse_html(html)
        content = find_article_content(soup)
        clean_content(content)
        result = analyze_content(content, audit["blog_url"], api_key=api_key)
        if result.get("error"):
            return jsonify(success=False, error=result["error"])
        save_content_verification(audit_id, result)
        return jsonify(success=True, result=result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/serp-analyze", methods=["POST"])
def seo_audit_serp_analyze(audit_id):
    """One-click: search keyword → scrape top results → save as competitors + return gap analysis."""
    data = request.get_json()
    keyword = data.get("keyword", "").strip()
    api_key = data.get("api_key", "").strip()
    if not keyword:
        return jsonify(success=False, error="Keyword required")

    try:
        pipeline = full_serp_pipeline(
            keyword, num_results=6, serp_api_key=api_key,
            location=data.get("location", ""), hl=data.get("hl", "en"),
            gl=data.get("gl", "us"), google_domain=data.get("google_domain", "google.com"),
        )
        scraped = pipeline["competitors"]

        # Save as competitors
        delete_competitors(audit_id)
        competitors = []
        for i, comp in enumerate(scraped):
            comp_id = save_competitor(audit_id, comp["url"], comp.get("title", ""), i + 1, comp.get("content", ""))
            if comp["headings"]:
                save_headings(audit_id, comp["headings"], competitor_id=comp_id)
            competitors.append({
                "id": comp_id, "url": comp["url"], "title": comp.get("title", ""),
                "headings": comp["headings"], "content": comp.get("content", ""),
                "error": comp.get("error"),
            })

        user_headings_raw = get_headings(audit_id)
        user_headings = [{"level": h["heading_level"], "text": h["heading_text"]} for h in user_headings_raw]

        comp_headings_for_gap = [{"headings": c["headings"]} for c in competitors]
        gap_analysis = build_gap_analysis(user_headings, comp_headings_for_gap)

        update_audit(audit_id, status="competitors_done")

        return jsonify(
            success=True,
            competitors=competitors,
            user_headings=user_headings,
            gap_analysis=gap_analysis,
            ai_overview=pipeline.get("ai_overview"),
            featured_snippet=pipeline.get("featured_snippet"),
            paa_questions=pipeline.get("paa_questions", []),
            related_searches=pipeline.get("related_searches", []),
        )
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/competitors", methods=["POST"])
def seo_audit_competitors(audit_id):
    data = request.get_json()
    urls = data.get("urls", [])
    if not urls:
        return jsonify(success=False, error="No competitor URLs provided")

    # Clear previous competitors
    delete_competitors(audit_id)

    # Scrape all competitor headings
    results = scrape_competitor_headings(urls[:6])
    competitors = []

    for i, comp in enumerate(results):
        comp_id = save_competitor(audit_id, comp["url"], comp.get("title", ""), i + 1, comp.get("content", ""))
        if comp["headings"]:
            save_headings(audit_id, comp["headings"], competitor_id=comp_id)
        competitors.append({
            "id": comp_id,
            "url": comp["url"],
            "title": comp.get("title", ""),
            "headings": comp["headings"],
            "content": comp.get("content", ""),
            "error": comp.get("error"),
        })

    user_headings_raw = get_headings(audit_id)
    user_headings = [{"level": h["heading_level"], "text": h["heading_text"]} for h in user_headings_raw]

    # Build gap analysis
    comp_headings_for_gap = [{"headings": c["headings"]} for c in competitors]
    gap_analysis = build_gap_analysis(user_headings, comp_headings_for_gap)

    update_audit(audit_id, status="competitors_done")
    return jsonify(success=True, user_headings=user_headings, competitors=competitors, gap_analysis=gap_analysis)


@app.route("/seo-audit/<int:audit_id>/competitors/auto", methods=["POST"])
def seo_audit_auto_discover(audit_id):
    data = request.get_json()
    api_key = data.get("api_key", "").strip()   # optional
    keyword = data.get("keyword", "").strip()

    audit = get_audit(audit_id)
    if not audit:
        return jsonify(success=False, error="Audit not found")

    search_kw = keyword or audit.get("target_keyword", "")
    if not search_kw:
        return jsonify(success=False, error="Set target keyword first")

    result = search_serp(search_kw, api_key)
    return jsonify(success=True, **result)


def _serp_params(data):
    return {
        "api_key": data.get("api_key", "").strip(),
        "keyword": data.get("keyword", "").strip(),
        "location": data.get("location", "").strip(),
        "hl": data.get("hl", "en").strip(),
        "gl": data.get("gl", "us").strip(),
        "google_domain": data.get("google_domain", "google.com").strip(),
    }


@app.route("/seo-audit/<int:audit_id>/ai-overview", methods=["POST"])
def seo_audit_ai_overview(audit_id):
    """Generate AI Overview by reading all saved competitor content with Groq."""
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify(success=False, error="Groq API key required")
    try:
        audit = get_audit(audit_id)
        if not audit:
            return jsonify(success=False, error="Audit not found")
        competitors = get_competitors(audit_id)
        comp_data = []
        for comp in competitors:
            comp_headings_raw = get_headings(audit_id, competitor_id=comp["id"])
            comp_data.append({
                "url": comp["url"],
                "title": comp.get("title", ""),
                "content": comp.get("content_text", ""),
                "headings": [{"level": h["heading_level"], "text": h["heading_text"]} for h in comp_headings_raw],
            })
        keyword = audit.get("target_keyword") or data.get("keyword", "")
        result = generate_ai_overview(keyword, comp_data, api_key)
        if result.get("error"):
            return jsonify(success=False, error=result["error"])
        return jsonify(success=True, overview=result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/api/serp", methods=["POST"])
def api_serp():
    """Standalone SERP search — no audit_id required."""
    p = _serp_params(request.get_json() or {})
    if not p["keyword"]:
        return jsonify(success=False, error="Keyword required")
    try:
        result = search_serp(p["keyword"], p["api_key"], num_results=10,
                             location=p["location"], hl=p["hl"], gl=p["gl"],
                             google_domain=p["google_domain"])
        return jsonify(success=True, keyword=p["keyword"], **result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/serp", methods=["POST"])
def seo_audit_serp(audit_id):
    p = _serp_params(request.get_json() or {})
    if not p["keyword"]:
        return jsonify(success=False, error="Keyword required")
    try:
        result = search_serp(p["keyword"], p["api_key"], num_results=10,
                             location=p["location"], hl=p["hl"], gl=p["gl"],
                             google_domain=p["google_domain"])
        return jsonify(success=True, keyword=p["keyword"], **result)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/recommend", methods=["POST"])
def seo_audit_recommend(audit_id):
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify(success=False, error="Groq API key required")

    try:
        # Gather all data
        user_headings_raw = get_headings(audit_id)
        user_headings = [{"level": h["heading_level"], "text": h["heading_text"]} for h in user_headings_raw]

        if not user_headings:
            return jsonify(success=False, error="No blog headings found. Please analyze a blog URL in Step 1 first.")

        competitors = get_competitors(audit_id)
        comp_data = []
        for comp in competitors:
            comp_headings_raw = get_headings(audit_id, competitor_id=comp["id"])
            comp_data.append({
                "url": comp["url"],
                "title": comp.get("title", ""),
                "headings": [{"level": h["heading_level"], "text": h["heading_text"]} for h in comp_headings_raw],
            })

        keywords = get_keywords(audit_id)
        kw_data = [{"keyword": k["keyword"], "volume": k.get("search_volume")} for k in keywords]

        guidelines = get_guidelines()

        result = generate_heading_recommendation(user_headings, comp_data, kw_data, guidelines, api_key)

        if result.get("error"):
            return jsonify(success=False, error=result["error"])

        # Save recommendations to DB (with diff_status + confidence)
        recs_to_save = []
        for r in result.get("recommendations", []):
            recs_to_save.append({
                "level": r.get("level", 2),
                "text": r.get("text", ""),
                "is_gap": 1 if r.get("is_gap") else 0,
                "reason": r.get("reason", ""),
                "diff_status": r.get("diff_status", "new"),
                "confidence": r.get("confidence", 0),
            })
        save_recommendations(audit_id, recs_to_save)

        # Save specialist analyses to DB
        if result.get("specialist_analyses"):
            save_specialist_analyses(audit_id, result["specialist_analyses"])

        update_audit(audit_id, status="recommended")

        return jsonify(
            success=True,
            recommendations=result.get("recommendations", []),
            summary=result.get("summary", ""),
            paa_questions=result.get("paa_questions", []),
            specialist_analyses=result.get("specialist_analyses", {}),
            key_insights=result.get("key_insights", {}),
            errors=result.get("errors"),
            user_headings=user_headings,
        )
    except Exception as e:
        return jsonify(success=False, error=str(e))


@app.route("/seo-audit/<int:audit_id>/recommendations", methods=["GET"])
def seo_audit_get_recommendations(audit_id):
    recs = get_recommendations(audit_id)
    return jsonify(success=True, recommendations=recs)


@app.route("/seo-audit/<int:audit_id>/recommendations", methods=["PUT"])
def seo_audit_update_recommendations(audit_id):
    data = request.get_json()
    action = data.get("action")

    if action == "delete":
        rec_id = data.get("rec_id")
        if rec_id:
            delete_recommendation(rec_id)
        return jsonify(success=True)

    if action == "add":
        recs = get_recommendations(audit_id)
        sort_order = len(recs)
        new_id = add_recommendation(audit_id, data.get("heading_level", 2), data.get("heading_text", "New Section"), sort_order)
        return jsonify(success=True, id=new_id)

    rec_id = data.get("rec_id")
    if rec_id:
        kwargs = {}
        if "heading_level" in data:
            kwargs["heading_level"] = data["heading_level"]
        if "heading_text" in data:
            kwargs["heading_text"] = data["heading_text"]
        if "status" in data:
            kwargs["status"] = data["status"]
        if "user_notes" in data:
            kwargs["user_notes"] = data["user_notes"]
        if kwargs:
            update_recommendation(rec_id, **kwargs)

    return jsonify(success=True)


@app.route("/seo-audit/<int:audit_id>/plan", methods=["POST"])
def seo_audit_generate_plan(audit_id):
    data = request.get_json()
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify(success=False, error="Groq API key required")

    audit = get_audit(audit_id)
    if not audit:
        return jsonify(success=False, error="Audit not found")

    audit_data = {
        "audit": audit,
        "headings": get_headings(audit_id),
        "competitors": get_competitors(audit_id),
        "recommendations": get_recommendations(audit_id),
        "keywords": get_keywords(audit_id),
        "guidelines": get_guidelines(),
    }

    result = generate_content_plan(audit_data, api_key)
    if result.get("error") and not result.get("plan"):
        return jsonify(success=False, error=result["error"])

    save_plan(audit_id, result["plan"])
    update_audit(audit_id, status="completed")

    return jsonify(success=True, plan=result["plan"], warning=result.get("error"))


@app.route("/seo-audit/<int:audit_id>/plan", methods=["GET"])
def seo_audit_get_plan(audit_id):
    plan = get_plan(audit_id)
    if not plan:
        return jsonify(success=False, error="No plan found")
    return jsonify(success=True, plan=plan["plan"])


@app.route("/seo-audit/<int:audit_id>/export")
def seo_audit_export(audit_id):
    plan_data = get_plan(audit_id)
    audit = get_audit(audit_id)
    if not plan_data or not audit:
        return "No plan found", 404

    plan = plan_data["plan"]
    builder = DocxBuilder(audit.get("blog_url", ""))

    # Title
    builder.add_heading(plan.get("title", audit.get("blog_title", "Content Plan")), level=0)
    builder.doc.add_paragraph("")

    # Meta info
    if plan.get("target_keyword"):
        p = builder.doc.add_paragraph()
        p.add_run("Target Keyword: ").bold = True
        p.add_run(plan["target_keyword"])
    if plan.get("meta_title"):
        p = builder.doc.add_paragraph()
        p.add_run("Meta Title: ").bold = True
        p.add_run(plan["meta_title"])
    if plan.get("meta_description"):
        p = builder.doc.add_paragraph()
        p.add_run("Meta Description: ").bold = True
        p.add_run(plan["meta_description"])
    if plan.get("total_word_count"):
        p = builder.doc.add_paragraph()
        p.add_run("Total Word Count: ").bold = True
        p.add_run(str(plan["total_word_count"]))

    builder.doc.add_paragraph("")

    # Sections
    for sec in plan.get("sections", []):
        heading_text = sec.get("heading", "")
        # Parse H level from heading text like "H2: Section Name"
        level = 2
        if heading_text.startswith("H"):
            try:
                level = int(heading_text[1])
                heading_text = heading_text[3:].strip(": ")
            except (ValueError, IndexError):
                pass

        gap_label = " [CONTENT GAP]" if sec.get("is_gap") else ""
        builder.add_heading(heading_text + gap_label, level=level)

        if sec.get("key_points"):
            for point in sec["key_points"]:
                builder.add_list_item(point, ordered=False)

        if sec.get("keywords_to_include"):
            p = builder.doc.add_paragraph()
            p.add_run("Keywords: ").bold = True
            p.add_run(", ".join(sec["keywords_to_include"]))

        if sec.get("word_count"):
            p = builder.doc.add_paragraph()
            p.add_run(f"Suggested word count: ~{sec['word_count']} words")

        if sec.get("notes"):
            p = builder.doc.add_paragraph()
            p.add_run("Notes: ").bold = True
            p.add_run(sec["notes"])

        builder.doc.add_paragraph("")

    # Source
    builder.doc.add_paragraph("")
    source_para = builder.doc.add_paragraph()
    source_para.add_run("Source: ").bold = True
    add_hyperlink(source_para, audit.get("blog_url", ""), audit.get("blog_url", ""))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_title = re.sub(r"[^\w\s-]", "", plan.get("title", "content-plan"))[:60].strip()
    safe_title = re.sub(r"[\s]+", "_", safe_title)
    filename = f"{safe_title}_SEO_Plan.docx"
    filepath = os.path.join(OUTPUT_DIR, filename)
    builder.save(filepath)

    return send_file(filepath, as_attachment=True, download_name=filename)


# ===================== Guidelines Routes =====================

@app.route("/guidelines", methods=["GET"])
def guidelines_list():
    return jsonify(success=True, guidelines=get_guidelines())


@app.route("/guidelines", methods=["POST"])
def guidelines_create():
    data = request.get_json()
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    category = data.get("category", "general")
    if not title or not content:
        return jsonify(success=False, error="Title and content required")
    gid = save_guideline(title, content, category)
    return jsonify(success=True, id=gid)


@app.route("/guidelines/<int:gid>", methods=["PUT"])
def guidelines_update(gid):
    data = request.get_json()
    update_guideline(gid, data.get("title"), data.get("content"), data.get("category"))
    return jsonify(success=True)


@app.route("/guidelines/<int:gid>", methods=["DELETE"])
def guidelines_delete(gid):
    delete_guideline(gid)
    return jsonify(success=True)


def main():
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
