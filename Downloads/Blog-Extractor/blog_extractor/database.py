"""SQLite database layer for SEO content audits."""

import json
import os
import sqlite3
from datetime import datetime

from .config import DATABASE_PATH

def _get_db_path():
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)
    return DATABASE_PATH

def get_db():
    db = sqlite3.connect(_get_db_path())
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS seo_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blog_url TEXT NOT NULL,
            blog_title TEXT,
            target_keyword TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'draft',
            content_verification_json TEXT,
            specialist_analysis_json TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL REFERENCES seo_audits(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            search_volume INTEGER,
            keyword_difficulty REAL,
            cpc REAL,
            keyword_type TEXT DEFAULT 'related'
        );

        CREATE TABLE IF NOT EXISTS audit_competitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL REFERENCES seo_audits(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            title TEXT,
            position INTEGER,
            scraped_at TIMESTAMP,
            content_text TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_headings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL REFERENCES seo_audits(id) ON DELETE CASCADE,
            competitor_id INTEGER REFERENCES audit_competitors(id) ON DELETE CASCADE,
            heading_level INTEGER NOT NULL,
            heading_text TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            source TEXT DEFAULT 'scraped'
        );

        CREATE TABLE IF NOT EXISTS audit_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL REFERENCES seo_audits(id) ON DELETE CASCADE,
            heading_level INTEGER NOT NULL,
            heading_text TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            user_notes TEXT,
            change_reason TEXT,
            is_gap INTEGER DEFAULT 0,
            confidence INTEGER DEFAULT 0,
            diff_status TEXT DEFAULT 'new'
        );

        CREATE TABLE IF NOT EXISTS content_guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS content_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id INTEGER NOT NULL REFERENCES seo_audits(id) ON DELETE CASCADE,
            plan_json TEXT NOT NULL,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()

    # Migrations — add columns that didn't exist in older DB versions
    migrations = [
        ("seo_audits", "content_verification_json", "TEXT"),
        ("seo_audits", "specialist_analysis_json", "TEXT"),
        ("audit_recommendations", "confidence", "INTEGER DEFAULT 0"),
        ("audit_recommendations", "diff_status", "TEXT DEFAULT 'new'"),
        ("audit_recommendations", "is_gap", "INTEGER DEFAULT 0"),
        ("audit_competitors", "content_text", "TEXT"),
    ]
    existing = {
        (row[0], row[1])
        for table, _, _ in migrations
        for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        # Rebuild: iterate each table once
    }
    # Simpler approach: just try each ALTER TABLE, ignore if column already exists
    for table, col, col_def in migrations:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            db.commit()
        except Exception:
            pass  # Column already exists

    db.close()


# --- Audit CRUD ---

def create_audit(blog_url, blog_title="", target_keyword=""):
    db = get_db()
    cur = db.execute(
        "INSERT INTO seo_audits (blog_url, blog_title, target_keyword) VALUES (?, ?, ?)",
        (blog_url, blog_title, target_keyword),
    )
    audit_id = cur.lastrowid
    db.commit()
    db.close()
    return audit_id

def get_audit(audit_id):
    db = get_db()
    row = db.execute("SELECT * FROM seo_audits WHERE id = ?", (audit_id,)).fetchone()
    db.close()
    return dict(row) if row else None

def save_content_verification(audit_id, findings):
    db = get_db()
    db.execute("UPDATE seo_audits SET content_verification_json = ? WHERE id = ?",
               (json.dumps(findings), audit_id))
    db.commit()
    db.close()

def get_content_verification(audit_id):
    db = get_db()
    row = db.execute("SELECT content_verification_json FROM seo_audits WHERE id = ?", (audit_id,)).fetchone()
    db.close()
    if row and row["content_verification_json"]:
        return json.loads(row["content_verification_json"])
    return None

def save_specialist_analyses(audit_id, analyses):
    db = get_db()
    db.execute("UPDATE seo_audits SET specialist_analysis_json = ? WHERE id = ?",
               (json.dumps(analyses), audit_id))
    db.commit()
    db.close()

def get_specialist_analyses(audit_id):
    db = get_db()
    row = db.execute("SELECT specialist_analysis_json FROM seo_audits WHERE id = ?", (audit_id,)).fetchone()
    db.close()
    if row and row["specialist_analysis_json"]:
        return json.loads(row["specialist_analysis_json"])
    return None

def update_audit(audit_id, **kwargs):
    db = get_db()
    allowed = {"blog_title", "target_keyword", "status"}
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if sets:
        sets.append("updated_at = ?")
        vals.append(datetime.now().isoformat())
        vals.append(audit_id)
        db.execute(f"UPDATE seo_audits SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()
    db.close()

def list_audits():
    db = get_db()
    rows = db.execute("SELECT * FROM seo_audits ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]


# --- Keywords ---

def save_keywords(audit_id, keywords):
    db = get_db()
    db.execute("DELETE FROM audit_keywords WHERE audit_id = ?", (audit_id,))
    for kw in keywords:
        db.execute(
            "INSERT INTO audit_keywords (audit_id, keyword, search_volume, keyword_difficulty, cpc, keyword_type) VALUES (?, ?, ?, ?, ?, ?)",
            (audit_id, kw["keyword"], kw.get("volume"), kw.get("difficulty"), kw.get("cpc"), kw.get("type", "related")),
        )
    db.commit()
    db.close()

def get_keywords(audit_id):
    db = get_db()
    rows = db.execute("SELECT * FROM audit_keywords WHERE audit_id = ?", (audit_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


# --- Competitors ---

def save_competitor(audit_id, url, title="", position=0, content_text=""):
    db = get_db()
    cur = db.execute(
        "INSERT INTO audit_competitors (audit_id, url, title, position, scraped_at, content_text) VALUES (?, ?, ?, ?, ?, ?)",
        (audit_id, url, title, position, datetime.now().isoformat(), content_text or ""),
    )
    comp_id = cur.lastrowid
    db.commit()
    db.close()
    return comp_id

def get_competitors(audit_id):
    db = get_db()
    rows = db.execute("SELECT * FROM audit_competitors WHERE audit_id = ? ORDER BY position", (audit_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def delete_competitors(audit_id):
    db = get_db()
    db.execute("DELETE FROM audit_headings WHERE audit_id = ? AND competitor_id IS NOT NULL", (audit_id,))
    db.execute("DELETE FROM audit_competitors WHERE audit_id = ?", (audit_id,))
    db.commit()
    db.close()


# --- Headings ---

def save_headings(audit_id, headings, competitor_id=None, source="scraped"):
    db = get_db()
    if competitor_id:
        db.execute("DELETE FROM audit_headings WHERE audit_id = ? AND competitor_id = ?", (audit_id, competitor_id))
    else:
        db.execute("DELETE FROM audit_headings WHERE audit_id = ? AND competitor_id IS NULL", (audit_id,))
    for i, h in enumerate(headings):
        db.execute(
            "INSERT INTO audit_headings (audit_id, competitor_id, heading_level, heading_text, sort_order, source) VALUES (?, ?, ?, ?, ?, ?)",
            (audit_id, competitor_id, h["level"], h["text"], i, source),
        )
    db.commit()
    db.close()

def get_headings(audit_id, competitor_id=None):
    db = get_db()
    if competitor_id:
        rows = db.execute("SELECT * FROM audit_headings WHERE audit_id = ? AND competitor_id = ? ORDER BY sort_order", (audit_id, competitor_id)).fetchall()
    else:
        rows = db.execute("SELECT * FROM audit_headings WHERE audit_id = ? AND competitor_id IS NULL ORDER BY sort_order", (audit_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def get_all_competitor_headings(audit_id):
    db = get_db()
    rows = db.execute(
        "SELECT h.*, c.url as comp_url, c.title as comp_title FROM audit_headings h JOIN audit_competitors c ON h.competitor_id = c.id WHERE h.audit_id = ? ORDER BY c.position, h.sort_order",
        (audit_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


# --- Recommendations ---

def save_recommendations(audit_id, recs):
    db = get_db()
    db.execute("DELETE FROM audit_recommendations WHERE audit_id = ?", (audit_id,))
    for i, r in enumerate(recs):
        db.execute(
            "INSERT INTO audit_recommendations (audit_id, heading_level, heading_text, sort_order, status, change_reason, is_gap, confidence, diff_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, r["level"], r["text"], i, r.get("status", "pending"), r.get("reason", ""),
             r.get("is_gap", 0), r.get("confidence", 0), r.get("diff_status", "new")),
        )
    db.commit()
    db.close()

def get_recommendations(audit_id):
    db = get_db()
    rows = db.execute("SELECT * FROM audit_recommendations WHERE audit_id = ? ORDER BY sort_order", (audit_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def update_recommendation(rec_id, **kwargs):
    db = get_db()
    allowed = {"heading_level", "heading_text", "status", "user_notes", "sort_order"}
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if sets:
        vals.append(rec_id)
        db.execute(f"UPDATE audit_recommendations SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()
    db.close()

def delete_recommendation(rec_id):
    db = get_db()
    db.execute("DELETE FROM audit_recommendations WHERE id = ?", (rec_id,))
    db.commit()
    db.close()

def add_recommendation(audit_id, level, text, sort_order):
    db = get_db()
    cur = db.execute(
        "INSERT INTO audit_recommendations (audit_id, heading_level, heading_text, sort_order, status) VALUES (?, ?, ?, ?, 'pending')",
        (audit_id, level, text, sort_order),
    )
    rec_id = cur.lastrowid
    db.commit()
    db.close()
    return rec_id


# --- Content Guidelines ---

def save_guideline(title, content, category="general"):
    db = get_db()
    cur = db.execute(
        "INSERT INTO content_guidelines (title, content, category) VALUES (?, ?, ?)",
        (title, content, category),
    )
    gid = cur.lastrowid
    db.commit()
    db.close()
    return gid

def get_guidelines():
    db = get_db()
    rows = db.execute("SELECT * FROM content_guidelines ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]

def update_guideline(gid, title=None, content=None, category=None):
    db = get_db()
    sets = []
    vals = []
    if title is not None:
        sets.append("title = ?")
        vals.append(title)
    if content is not None:
        sets.append("content = ?")
        vals.append(content)
    if category is not None:
        sets.append("category = ?")
        vals.append(category)
    if sets:
        vals.append(gid)
        db.execute(f"UPDATE content_guidelines SET {', '.join(sets)} WHERE id = ?", vals)
        db.commit()
    db.close()

def delete_guideline(gid):
    db = get_db()
    db.execute("DELETE FROM content_guidelines WHERE id = ?", (gid,))
    db.commit()
    db.close()


# --- Content Plans ---

def save_plan(audit_id, plan_dict):
    db = get_db()
    db.execute(
        "INSERT INTO content_plans (audit_id, plan_json) VALUES (?, ?)",
        (audit_id, json.dumps(plan_dict)),
    )
    db.commit()
    db.close()

def get_plan(audit_id):
    db = get_db()
    row = db.execute("SELECT * FROM content_plans WHERE audit_id = ? ORDER BY generated_at DESC LIMIT 1", (audit_id,)).fetchone()
    db.close()
    if row:
        result = dict(row)
        result["plan"] = json.loads(result["plan_json"])
        return result
    return None
