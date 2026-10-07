#!/usr/bin/env python3
"""LinkedIn-only Job Alert Bot v1.38.

Pipeline:
  LinkedIn/Apify -> rotating search coverage -> hard filters -> relevance ranking
  -> deduplication -> Telegram -> SQLite application history

No other job sources are included.
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sqlite3
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from apify_client import ApifyClient

import config
from relevance import score_job, should_alert

logger = logging.getLogger("job_alert_bot")


def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S%z")
    file_handler = RotatingFileHandler(config.LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)


# ---------------------------------------------------------------------------
# Database / migration
# ---------------------------------------------------------------------------

JOB_COLUMNS = {
    "relevance_score": "REAL",
    "relevance_band": "TEXT",
    "match_reason": "TEXT",
    "negative_signals": "TEXT",
    "first_seen_at": "TEXT",
    "alert_status": "TEXT DEFAULT 'ALERTED'",
    "applied_at": "TEXT",
    "status_updated_at": "TEXT",
    "notes": "TEXT",
}
RUN_COLUMNS = {
    "skipped_unknown_date": "INTEGER DEFAULT 0",
    "skipped_wrong_location": "INTEGER DEFAULT 0",
    "skipped_low_relevance": "INTEGER DEFAULT 0",
    "anomaly_flag": "INTEGER DEFAULT 0",
}


_ALLOWED_MIGRATION_TABLES = {"jobs", "run_history"}


def _sanitize_log(value: Any) -> str:
    """Collapse line-breaking control characters before logging untrusted text."""
    return re.sub(r"[\r\n]+", " ", str(value))


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    if table not in _ALLOWED_MIGRATION_TABLES:
        raise ValueError("_add_missing_columns: unknown table %r" % table)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))
            logger.info("DB migration: added %s.%s", table, name)


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            job_key TEXT PRIMARY KEY, title TEXT, company TEXT, country TEXT,
            location TEXT, url TEXT, posted_at TEXT, description TEXT,
            matched_keyword TEXT, fetched_at TEXT, alerted_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS run_history (
            run_id TEXT, timestamp TEXT, day_of_week TEXT, schedule_slot TEXT,
            keyword TEXT, country TEXT, jobs_fetched INTEGER, jobs_matched INTEGER,
            jobs_alerted INTEGER, skipped_stale INTEGER, skipped_duplicate INTEGER,
            skipped_no_keyword INTEGER, avg_latency_seconds REAL,
            apify_cost_estimate REAL, error_count INTEGER, duration_seconds REAL,
            notes TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bot_state (
            state_key TEXT PRIMARY KEY, state_value TEXT, updated_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS application_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            note TEXT
        )"""
    )
    _add_missing_columns(conn, "jobs", JOB_COLUMNS)
    _add_missing_columns(conn, "run_history", RUN_COLUMNS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_history_combo ON run_history(keyword, country, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_history_time ON run_history(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(alert_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_app_events_job ON application_events(job_key, changed_at)")
    conn.commit()
    return conn


def already_alerted(conn: sqlite3.Connection, job_key: str, url: str) -> bool:
    linkedin_key = job_key if job_key.startswith("linkedin:") else ""
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE job_key=? OR url=? OR (? <> '' AND job_key=?) LIMIT 1",
        (job_key, url, linkedin_key, linkedin_key),
    ).fetchone()
    return row is not None


def record_job(conn: sqlite3.Connection, job: Dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO jobs (
            job_key,title,company,country,location,url,posted_at,description,
            matched_keyword,fetched_at,alerted_at,relevance_score,relevance_band,
            match_reason,negative_signals,first_seen_at,alert_status,status_updated_at,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job["job_key"], job["title"], job["company"], job["country"], job["location"],
            job["url"], job["posted_at"].isoformat(), job["description"], job.get("matched_keyword"),
            job["fetched_at"].isoformat(), now, job.get("relevance_score"), job.get("relevance_band"),
            job.get("match_reason"), ", ".join(job.get("negative_signals", [])),
            job.get("first_seen_at", job["fetched_at"].isoformat()), "ALERTED", now, job.get("notes"),
        ),
    )
    conn.execute(
        "INSERT INTO application_events(job_key,old_status,new_status,changed_at,note) VALUES(?,?,?,?,?)",
        (job["job_key"], None, "ALERTED", now, "Telegram alert sent"),
    )
    conn.commit()


def record_run_row(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO run_history (
            run_id,timestamp,day_of_week,schedule_slot,keyword,country,jobs_fetched,
            jobs_matched,jobs_alerted,skipped_stale,skipped_duplicate,skipped_no_keyword,
            avg_latency_seconds,apify_cost_estimate,error_count,duration_seconds,notes,
            skipped_unknown_date,skipped_wrong_location,skipped_low_relevance,anomaly_flag
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row["run_id"], row["timestamp"], row.get("day_of_week"), row.get("schedule_slot"),
            row.get("keyword"), row.get("country"), row.get("jobs_fetched", 0), row.get("jobs_matched", 0),
            row.get("jobs_alerted", 0), row.get("skipped_stale", 0), row.get("skipped_duplicate", 0),
            row.get("skipped_no_keyword", 0), row.get("avg_latency_seconds"), row.get("apify_cost_estimate", 0.0),
            row.get("error_count", 0), row.get("duration_seconds"), row.get("notes"),
            row.get("skipped_unknown_date", 0), row.get("skipped_wrong_location", 0),
            row.get("skipped_low_relevance", 0), row.get("anomaly_flag", 0),
        ),
    )
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT state_value FROM bot_state WHERE state_key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO bot_state(state_key,state_value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(state_key) DO UPDATE SET state_value=excluded.state_value,updated_at=excluded.updated_at",
        (key, value, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def update_job_status(conn: sqlite3.Connection, job_key: str, status: str, note: str = "") -> bool:
    status = status.upper()
    if status not in config.APPLICATION_STATUSES:
        raise ValueError("Invalid status: %s" % status)
    row = conn.execute("SELECT alert_status FROM jobs WHERE job_key=?", (job_key,)).fetchone()
    if not row:
        return False
    old_status = row[0]
    now = datetime.now(timezone.utc).isoformat()
    applied_at = now if status == "APPLIED" else None
    conn.execute(
        "UPDATE jobs SET alert_status=?, status_updated_at=?, applied_at=COALESCE(?, applied_at), notes=? WHERE job_key=?",
        (status, now, applied_at, note, job_key),
    )
    conn.execute(
        "INSERT INTO application_events(job_key,old_status,new_status,changed_at,note) VALUES(?,?,?,?,?)",
        (job_key, old_status, status, now, note),
    )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Search coverage / cost / anomaly control
# ---------------------------------------------------------------------------


def all_search_combos() -> List[Tuple[str, str]]:
    return [(keyword, country) for keyword in config.SEARCH_KEYWORDS for country in config.COUNTRIES]


def select_search_combos(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    combos = all_search_combos()
    if not combos:
        return []
    cursor = int(get_state(conn, "search_rotation_cursor", "0")) % len(combos)
    return [combos[(cursor + i) % len(combos)] for i in range(min(config.SEARCH_ROTATION_SIZE, len(combos)))]


def advance_search_cursor(conn: sqlite3.Connection, combo: Tuple[str, str]) -> None:
    combos = all_search_combos()
    if combo not in combos:
        return
    next_cursor = (combos.index(combo) + 1) % len(combos)
    set_state(conn, "search_rotation_cursor", str(next_cursor))


def today_utc_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def apify_cost_today(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(apify_cost_estimate),0) FROM run_history WHERE timestamp>=? AND keyword!='__RUN_TOTAL__'",
        (today_utc_start().isoformat(),),
    ).fetchone()
    return float(row[0] or 0.0)


def historical_anomaly(conn: sqlite3.Connection, keyword: str, country: str, current_count: int) -> Tuple[bool, str]:
    rows = conn.execute(
        """SELECT jobs_fetched FROM run_history
           WHERE keyword=? AND country=? AND keyword!='__RUN_TOTAL__'
           ORDER BY timestamp DESC LIMIT ?""",
        (keyword, country, config.ANOMALY_LOOKBACK_RUNS),
    ).fetchall()
    history = [int(r[0] or 0) for r in rows]
    if len(history) < config.ANOMALY_MIN_HISTORY:
        return False, "insufficient history"
    baseline = statistics.median(history)
    if current_count == 0 and baseline >= config.ANOMALY_ZERO_FLOOR:
        return True, "result volume dropped to zero; median=%s" % int(baseline)
    if baseline <= 0:
        return False, "baseline zero"
    change = abs(current_count - baseline) / baseline
    if change >= config.ANOMALY_RELATIVE_CHANGE:
        return True, "result volume=%d vs median=%d (%.0f%% change)" % (current_count, int(baseline), change * 100)
    return False, "within historical range"


def country_holiday(country: str, now_gulf: datetime) -> bool:
    return now_gulf.strftime("%Y-%m-%d") in config.PUBLIC_HOLIDAYS.get(country, set())


# ---------------------------------------------------------------------------
# Schedule guards
# ---------------------------------------------------------------------------


def schedule_block_reason(now_gulf: datetime) -> Optional[str]:
    if config.IGNORE_SCHEDULE_GUARDS:
        return None
    if now_gulf.weekday() in config.NON_WORKING_WEEKDAYS:
        return "Gulf weekend (%s)" % now_gulf.strftime("%A")
    if now_gulf.hour not in config.SCHEDULE_HOURS:
        return "outside scheduled Gulf hour (%s:%02d)" % (now_gulf.hour, now_gulf.minute)
    if now_gulf.minute > config.SCHEDULE_HOUR_GRACE_MINUTES:
        return "outside scheduled minute window (%s:%02d)" % (now_gulf.hour, now_gulf.minute)
    return None


def schedule_slot(now_gulf: datetime) -> str:
    return config.SCHEDULE_HOURS.get(now_gulf.hour, "unscheduled(%s)" % now_gulf.strftime("%H:%M"))


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class Telegram:
    def __init__(self, token: str, chat_id: str) -> None:
        self.url = "%s/bot%s/sendMessage" % (config.TELEGRAM_API_BASE, token)
        self.chat_id = chat_id
        self.session = requests.Session()
        self._last_send_ts = 0.0

    def _post(self, text: str, disable_preview: bool) -> requests.Response:
        return self.session.post(
            self.url,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            },
            timeout=config.TELEGRAM_SEND_TIMEOUT_SECS,
        )

    def send(self, text: str, disable_preview: bool = False) -> bool:
        elapsed = time.monotonic() - self._last_send_ts
        if elapsed < config.TELEGRAM_MIN_SEND_INTERVAL_SECS:
            time.sleep(config.TELEGRAM_MIN_SEND_INTERVAL_SECS - elapsed)
        for attempt in range(1, config.TELEGRAM_MAX_RETRIES + 1):
            try:
                resp = self._post(text, disable_preview)
                self._last_send_ts = time.monotonic()
                if resp.ok:
                    return True
                if resp.status_code == 429:
                    try:
                        retry_after = int(resp.json().get("parameters", {}).get("retry_after", config.TELEGRAM_BACKOFF_SECS))
                    except Exception:
                        retry_after = config.TELEGRAM_BACKOFF_SECS
                    logger.warning("Telegram 429; retry_after=%ss; attempt=%d", retry_after, attempt)
                    time.sleep(retry_after)
                    continue
                if resp.status_code >= 500:
                    delay = config.TELEGRAM_BACKOFF_SECS * attempt
                    logger.warning("Telegram %s; retrying in %ss", resp.status_code, delay)
                    time.sleep(delay)
                    continue
                logger.error("Telegram permanent failure: %s %s", resp.status_code, resp.text[:300])
                return False
            except requests.RequestException as exc:
                logger.warning("Telegram network error attempt %d/%d: %s", attempt, config.TELEGRAM_MAX_RETRIES, exc)
                if attempt < config.TELEGRAM_MAX_RETRIES:
                    time.sleep(config.TELEGRAM_BACKOFF_SECS * attempt)
            except Exception as exc:
                logger.exception("Telegram unexpected error: %s", exc)
                return False
        return False


def escape_html(text: str) -> str:
    return html.escape(str(text), quote=False)


# ---------------------------------------------------------------------------
# Date / URL / location helpers
# ---------------------------------------------------------------------------

def parse_posted_at(raw: Any) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        ts = raw / 1000.0 if raw > 1e11 else raw
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(raw, str):
        text = raw.strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        lowered = text.lower()
        if "just now" in lowered or "moments ago" in lowered:
            return datetime.now(timezone.utc)
        match = re.search(r"(\d+)\s*(minute|min|hour|hr|day|week|month)s?\s*ago", lowered)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            deltas = {
                "minute": timedelta(minutes=amount), "min": timedelta(minutes=amount),
                "hour": timedelta(hours=amount), "hr": timedelta(hours=amount),
                "day": timedelta(days=amount), "week": timedelta(weeks=amount),
                "month": timedelta(days=30 * amount),
            }
            return datetime.now(timezone.utc) - deltas[unit]
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def humanize_age(posted_at: datetime) -> str:
    delta = datetime.now(timezone.utc) - posted_at
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 2:
        return "Just now"
    if minutes < 60:
        return "%d minutes ago" % minutes
    hours = minutes // 60
    if hours < 24:
        return "%d hour%s ago" % (hours, "s" if hours != 1 else "")
    days = hours // 24
    return "%d day%s ago" % (days, "s" if days != 1 else "")


def normalize_url(url: str) -> str:
    parts = urlsplit(str(url).strip())
    if not parts.netloc:
        return str(url).split("?")[0].rstrip("/")
    removable = {
        "trk", "trackingId", "trackingid", "refId", "refid", "lipi", "midToken",
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "mc_cid", "mc_eid",
    }
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in removable]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def linkedin_job_id(url: str) -> Optional[str]:
    m = re.search(r"/jobs/view/(?:[^/]+-)?(\d+)", url or "", flags=re.I)
    return m.group(1) if m else None


def validate_location(location: str, expected_country: str) -> Tuple[bool, str]:
    text = (location or "").lower().strip()
    if not text:
        return False, "missing location"
    # City/country vocabulary lives in config so a new target country needs no
    # code change — see config.COUNTRY_LOCATION_TERMS.
    expected = [x.lower() for x in config.COUNTRY_LOCATION_TERMS.get(expected_country, [])]
    foreign = [x.lower() for x in config.FOREIGN_LOCATION_TERMS]
    if not expected:
        return False, "no location terms configured for %s" % expected_country
    if any(x in text for x in foreign) and not any(x in text for x in expected):
        return False, "explicit foreign location"
    if any(x in text for x in expected):
        return True, "location matches %s" % expected_country
    # Remote is accepted only when the posting itself names the target country.
    if "remote" in text or "hybrid" in text:
        return False, "remote/hybrid country not confirmed"
    return False, "location does not identify %s" % expected_country


def extract_job(item: Dict[str, Any], country: str) -> Optional[Dict[str, Any]]:
    def pick(*keys: str) -> Any:
        for key in keys:
            value = item.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    url = pick("jobUrl", "url", "link", "jobPostingUrl", "applyUrl")
    title = pick("title", "jobTitle", "positionName")
    if not url or not title:
        return None
    company = pick("companyName", "company", "companyTitle", "employer") or "Not specified"
    location = pick("location", "jobLocation", "formattedLocation", "place") or ""
    description = pick("description", "descriptionText", "jobDescription", "descriptionHtml") or ""
    description = re.sub(r"<[^>]+>", " ", str(description))
    description = re.sub(r"\s+", " ", description).strip()
    posted_raw = pick("postedAt", "publishedAt", "postedDate", "listedAt", "postedTime", "datePosted", "postedTimeAgo")
    posted_at = parse_posted_at(posted_raw)
    canonical_url = normalize_url(str(url))
    # Stable LinkedIn numeric ID first; scraper IDs can change across runs.
    linked_id = linkedin_job_id(canonical_url)
    scraper_id = pick("id", "jobId", "jobPostingId")
    job_key = "linkedin:%s" % linked_id if linked_id else ("scraper:%s" % scraper_id if scraper_id else "url:%s" % canonical_url)
    return {
        "job_key": job_key, "title": str(title).strip(), "company": str(company).strip(),
        "country": country, "location": str(location).strip(), "url": canonical_url,
        "posted_at": posted_at, "description": description,
        "matched_keyword": None, "fetched_at": datetime.now(timezone.utc),
        "first_seen_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize_requirements(description: str) -> str:
    if not description:
        return "No description was provided in the posting. Open the link for full details."
    text = re.sub(r"[•\u2022\u25cf*\-]\s*", " ", description)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]
    if not sentences:
        return text[:config.REQUIREMENTS_SUMMARY_MAX_CHARS].strip() + "..."
    cues = ("experience", "require", "must", "should", "degree", "year", "knowledge", "skill", "familiar", "proficien", "candidate", "looking for")
    preferred = [s for s in sentences if any(c in s.lower() for c in cues)]
    summary = " ".join((preferred or sentences)[:4])
    if len(summary) > config.REQUIREMENTS_SUMMARY_MAX_CHARS:
        summary = summary[:config.REQUIREMENTS_SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return summary


def extract_job_signals(description: str) -> Dict[str, Any]:
    """Extract useful, explainable job facts without an external AI service."""
    text = re.sub(r"\s+", " ", description or "").strip()
    low = text.lower()
    years = []
    for m in re.finditer(r"(?:minimum\s+|at\s+least\s+|over\s+|around\s+)?(\d+)\s*\+?\s*(?:years?|yrs?)", low):
        try:
            years.append(int(m.group(1)))
        except ValueError:
            pass
    salary_matches = re.findall(r"(?:sar|qar|aed|usd|\$)\s?[0-9][0-9,]*(?:\s*(?:-|to)\s*[0-9][0-9,]*)?", low, flags=re.I)
    return {
        "experience_years": min(years) if years else None,
        "salary_mentions": list(dict.fromkeys(salary_matches[:3])),
        "shift_24x7": bool(re.search(r"24\s*/\s*7|24x7|rotational shift|rotating shift|night shift|shift work", low)),
        "arabic_required": bool(re.search(r"(?:fluent|proficient|native|mandatory|required|must).*arabic|arabic.*(?:required|mandatory|must|fluent|proficient|native)", low)),
        "visa_relocation": bool(re.search(r"visa sponsorship|work visa|employment visa|relocation|relocate", low)),
    }


def build_alert(job: Dict[str, Any]) -> str:
    reasons = "; ".join(job.get("match_reasons", [])) or "role relevance"
    families = ", ".join(job.get("matched_families", []))
    return (
        "<b>New LinkedIn Job Alert</b>\n\n"
        "<b>Job Title:</b> %s\n"
        "<b>Match Score:</b> %s/100 (%s)\n"
        "<b>Role Track:</b> %s\n"
        "<b>Why matched:</b> %s\n\n"
        "<b>Posted:</b> %s\n"
        "<b>Country:</b> %s\n"
        "<b>Location:</b> %s\n"
        "<b>Company:</b> %s\n"
        "<b>Experience:</b> %s\n"
        "<b>Shift:</b> %s\n"
        "<b>Arabic:</b> %s\n"
        "<b>Visa/Relocation:</b> %s\n\n"
        "<b>Job Requirements:</b>\n%s\n\n"
        "<b>Apply here:</b>\n%s"
    ) % (
        escape_html(job["title"]), escape_html(job.get("relevance_score", "")), escape_html(job.get("relevance_band", "")),
        escape_html(families or "Support"), escape_html(reasons), escape_html(humanize_age(job["posted_at"])),
        escape_html(job["country"]), escape_html(job["location"]), escape_html(job["company"]),
        escape_html((str(job.get("experience_years")) + "+ years" if job.get("experience_years") is not None else "Not stated")),
        escape_html("24x7/shift language" if job.get("shift_24x7") else "Not stated"),
        escape_html("Required/mentioned" if job.get("arabic_required") else "Not stated"),
        escape_html("Mentioned" if job.get("visa_relocation") else "Not stated"),
        escape_html(summarize_requirements(job["description"])), escape_html(job["url"]),
    )


# ---------------------------------------------------------------------------
# Apify
# ---------------------------------------------------------------------------

def fetch_jobs(client: ApifyClient, keyword: str, country: str) -> List[Dict[str, Any]]:
    run_input = {
        "keywords": [keyword], "location": country,
        "maxItems": config.MAX_RESULTS_PER_COMBO, "maxResults": config.MAX_RESULTS_PER_COMBO,
        "datePosted": "past24Hours", "publishedAt": "r86400",
    }
    run = client.actor(config.APIFY_ACTOR_ID).call(
        run_input=run_input, timeout_secs=config.APIFY_RUN_TIMEOUT_SECS, memory_mbytes=1024,
    )
    if not run or not run.get("defaultDatasetId"):
        logger.warning("Actor run returned no dataset for '%s' / %s", keyword, country)
        return []
    return list(client.dataset(run["defaultDatasetId"]).iterate_items(limit=config.MAX_RESULTS_PER_COMBO))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="LinkedIn-only job alert bot")
    parser.add_argument("--status", nargs=2, metavar=("JOB_KEY", "STATUS"), help="Update job lifecycle status")
    parser.add_argument("--note", default="", help="Note for --status")
    args = parser.parse_args()

    setup_logging()
    conn = init_db()

    if args.status:
        ok = update_job_status(conn, args.status[0], args.status[1], args.note)
        logger.info("Status update %s: %s", "successful" if ok else "job not found", args.status[0])
        conn.close()
        return 0 if ok else 2

    run_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    now_gulf = datetime.now(timezone.utc).astimezone(config.GULF_TZ)
    day_name = now_gulf.strftime("%A")
    slot = schedule_slot(now_gulf)
    logger.info("=" * 70)
    logger.info("Run %s starting | %s %s Gulf time | slot %s", run_id, day_name, now_gulf.strftime("%Y-%m-%d %H:%M"), slot)

    missing = [name for name, value in (("APIFY_API_TOKEN", config.APIFY_API_TOKEN), ("TELEGRAM_BOT_TOKEN", config.TELEGRAM_BOT_TOKEN), ("TELEGRAM_CHAT_ID", config.TELEGRAM_CHAT_ID)) if not value]
    if missing:
        logger.error("Missing environment variables: %s — aborting.", ", ".join(missing))
        conn.close()
        return 1

    # Catch the most common customization mistake: a target country added to
    # COUNTRIES without matching entries in COUNTRY_LOCATION_TERMS, which would
    # silently reject every posting for it.
    unconfigured = [c for c in config.COUNTRIES if not config.COUNTRY_LOCATION_TERMS.get(c)]
    if unconfigured:
        logger.error(
            "No COUNTRY_LOCATION_TERMS configured for: %s — every posting for those "
            "countries would be rejected. Add their cities in config.py — aborting.",
            ", ".join(unconfigured),
        )
        conn.close()
        return 1

    blocked = schedule_block_reason(now_gulf)
    if blocked:
        logger.info("Skipping run: %s", blocked)
        record_run_row(conn, {
            "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "day_of_week": day_name,
            "schedule_slot": slot, "duration_seconds": round(time.monotonic() - started, 2), "notes": "skipped: %s" % blocked,
        })
        conn.close()
        return 0

    telegram = Telegram(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
    client = ApifyClient(config.APIFY_API_TOKEN)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_JOB_AGE_HOURS)
    totals = {"fetched": 0, "matched": 0, "alerted": 0, "stale": 0, "unknown_date": 0, "wrong_location": 0, "duplicate": 0, "no_keyword": 0, "low_relevance": 0, "errors": 0, "holiday": 0}
    all_latencies: List[float] = []
    anomalies: List[str] = []
    circuit_breaker_tripped = False
    daily_cost_before = apify_cost_today(conn)
    combos = select_search_combos(conn)

    logger.info("Search rotation selected %d/%d combos: %s", len(combos), len(all_search_combos()), ", ".join("%s/%s" % x for x in combos))

    for search_keyword, country in combos:
        if country_holiday(country, now_gulf):
            totals["holiday"] += 1
            logger.info("Skipping %s/%s: country-specific holiday", search_keyword, country)
            advance_search_cursor(conn, (search_keyword, country))
            continue

        estimated_next = config.MAX_RESULTS_PER_COMBO * config.APIFY_COST_PER_1000_RESULTS / 1000.0
        if totals["fetched"] + config.MAX_RESULTS_PER_COMBO > config.SAFETY_MAX_RESULTS_PER_RUN:
            logger.warning("Per-run result guard reached; remaining combos skipped")
            circuit_breaker_tripped = True
            break
        if (totals["fetched"] * config.APIFY_COST_PER_1000_RESULTS / 1000.0) + estimated_next > config.MAX_APIFY_COST_PER_RUN:
            logger.warning("Per-run cost guard reached; remaining combos skipped")
            circuit_breaker_tripped = True
            break
        if daily_cost_before + (totals["fetched"] * config.APIFY_COST_PER_1000_RESULTS / 1000.0) + estimated_next > config.MAX_APIFY_COST_PER_DAY:
            logger.warning("Daily cost guard reached; remaining combos skipped")
            circuit_breaker_tripped = True
            break

        combo_started = time.monotonic()
        counts = {k: 0 for k in totals}
        latencies: List[float] = []
        note = None
        anomaly = 0
        try:
            items = fetch_jobs(client, search_keyword, country)
            counts["fetched"] = len(items)
            is_anomaly, anomaly_reason = historical_anomaly(conn, search_keyword, country, len(items))
            if is_anomaly:
                anomaly = 1
                anomalies.append("%s/%s: %s" % (search_keyword, country, anomaly_reason))
                logger.warning("Historical result-volume anomaly: %s/%s: %s", search_keyword, country, anomaly_reason)

            eligible_jobs: List[Dict[str, Any]] = []
            seen_in_combo = set()
            for item in items:
                job = extract_job(item, country)
                if not job:
                    continue
                if job["job_key"] in seen_in_combo:
                    counts["duplicate"] += 1
                    continue
                seen_in_combo.add(job["job_key"])
                if not job["posted_at"]:
                    counts["unknown_date"] += 1
                    continue
                if job["posted_at"] < cutoff or job["posted_at"] > datetime.now(timezone.utc) + timedelta(minutes=5):
                    counts["stale"] += 1
                    continue
                valid_location, _ = validate_location(job["location"], country)
                if not valid_location:
                    counts["wrong_location"] += 1
                    continue

                relevance = score_job(job["title"], job["description"])
                if not should_alert(relevance):
                    counts["low_relevance"] += 1
                    continue

                job["matched_keyword"] = relevance.get("matched_role") or search_keyword
                job["relevance_score"] = relevance["score"]
                job["relevance_band"] = relevance["band"]
                job["match_reason"] = "; ".join(relevance["reasons"])
                job["match_reasons"] = relevance["reasons"]
                job["negative_signals"] = relevance["negative_reasons"]
                job["matched_families"] = relevance.get("matched_families", [])
                job.update(extract_job_signals(job["description"]))
                counts["matched"] += 1

                if already_alerted(conn, job["job_key"], job["url"]):
                    counts["duplicate"] += 1
                    continue
                eligible_jobs.append(job)

            # Rank before sending so the strongest candidates are delivered first.
            eligible_jobs.sort(key=lambda x: (x.get("relevance_score", 0), x.get("posted_at")), reverse=True)
            if len(eligible_jobs) > config.MAX_ALERTS_PER_RUN:
                logger.info("Alert cap: %d eligible jobs reduced to top %d for this run", len(eligible_jobs), config.MAX_ALERTS_PER_RUN)
                eligible_jobs = eligible_jobs[:config.MAX_ALERTS_PER_RUN]

            for job in eligible_jobs:
                if telegram.send(build_alert(job)):
                    latency = (datetime.now(timezone.utc) - job["fetched_at"]).total_seconds()
                    latencies.append(latency)
                    counts["alerted"] += 1
                    record_job(conn, job)
                    logger.info(
                        "ALERT SENT | score=%s | %s | %s | %s | latency %.2fs | %s",
                        job["relevance_score"],
                        _sanitize_log(job["title"]),
                        _sanitize_log(job["company"]),
                        country,
                        latency,
                        _sanitize_log(job["url"]),
                    )
                else:
                    counts["errors"] += 1
                    logger.error(
                        "Alert failed; job remains unrecorded for retry: %s",
                        _sanitize_log(job["url"]),
                    )

        except Exception as exc:
            counts["errors"] += 1
            note = "%s: %s" % (type(exc).__name__, exc)
            logger.exception("Error on '%s' / %s: %s", search_keyword, country, exc)
            telegram.send(
                "<b>Job bot error</b>\n\nSearch: %s in %s\nProblem: %s\nDetails: %s" %
                (escape_html(search_keyword), escape_html(country), escape_html(type(exc).__name__), escape_html(str(exc)[:200])),
                disable_preview=True,
            )

        for key in totals:
            totals[key] += counts[key]
        all_latencies.extend(latencies)
        record_run_row(conn, {
            "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "day_of_week": day_name,
            "schedule_slot": slot, "keyword": search_keyword, "country": country,
            "jobs_fetched": counts["fetched"], "jobs_matched": counts["matched"], "jobs_alerted": counts["alerted"],
            "skipped_stale": counts["stale"], "skipped_duplicate": counts["duplicate"], "skipped_no_keyword": counts["no_keyword"],
            "avg_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "apify_cost_estimate": round(counts["fetched"] * config.APIFY_COST_PER_1000_RESULTS / 1000, 5),
            "error_count": counts["errors"], "duration_seconds": round(time.monotonic() - combo_started, 2),
            "notes": note, "skipped_unknown_date": counts["unknown_date"], "skipped_wrong_location": counts["wrong_location"],
            "skipped_low_relevance": counts["low_relevance"], "anomaly_flag": anomaly,
        })
        advance_search_cursor(conn, (search_keyword, country))

    duration = round(time.monotonic() - started, 2)
    cost = round(totals["fetched"] * config.APIFY_COST_PER_1000_RESULTS / 1000, 4)
    avg_latency = round(sum(all_latencies) / len(all_latencies), 3) if all_latencies else None
    logger.info(
        "Run %s finished %.2fs | fetched=%d matched=%d alerted=%d stale=%d unknown_date=%d wrong_location=%d duplicate=%d low_relevance=%d holiday=%d errors=%d cost=$%.4f",
        run_id, duration, totals["fetched"], totals["matched"], totals["alerted"], totals["stale"], totals["unknown_date"],
        totals["wrong_location"], totals["duplicate"], totals["low_relevance"], totals["holiday"], totals["errors"], cost,
    )

    if anomalies:
        telegram.send("<b>Job bot search-volume warning</b>\n\n" + "\n".join("• " + escape_html(x) for x in anomalies), disable_preview=True)

    record_run_row(conn, {
        "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "day_of_week": day_name,
        "schedule_slot": slot, "keyword": "__RUN_TOTAL__", "country": "__ALL__", "jobs_fetched": totals["fetched"],
        "jobs_matched": totals["matched"], "jobs_alerted": totals["alerted"], "skipped_stale": totals["stale"],
        "skipped_duplicate": totals["duplicate"], "skipped_no_keyword": totals["no_keyword"], "avg_latency_seconds": avg_latency,
        "apify_cost_estimate": cost, "error_count": totals["errors"], "duration_seconds": duration,
        "notes": "run summary; combos=%d/%d; circuit_breaker=%s; anomalies=%d" % (len(combos), len(all_search_combos()), circuit_breaker_tripped, len(anomalies)),
        "skipped_unknown_date": totals["unknown_date"], "skipped_wrong_location": totals["wrong_location"],
        "skipped_low_relevance": totals["low_relevance"], "anomaly_flag": 1 if anomalies or circuit_breaker_tripped else 0,
    })
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logging.getLogger("job_alert_bot").exception("Fatal error: %s", exc)
        try:
            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                Telegram(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID).send(
                    "<b>Job bot crashed</b>\n\nProblem: %s\nDetails: %s" % (escape_html(type(exc).__name__), escape_html(str(exc)[:200])),
                    disable_preview=True,
                )
        except Exception as notification_exc:
            logging.getLogger("job_alert_bot").error(
                "Fatal error notification failed: %s", type(notification_exc).__name__
            )
        sys.exit(1)
