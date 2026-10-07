"""Configuration for FirstQueue.

Everything you are likely to change lives in PART 1 (Your search profile).
PART 2 holds the relevance vocabulary, and PART 3 the operational tuning you
can usually leave alone.

Credentials are never stored here. They are read from environment variables,
which in production come from the `.env` file loaded by the systemd unit.
See .env.example and docs/SETUP.md.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "jobs.db")
LOG_PATH = os.path.join(BASE_DIR, "bot.log")

# ---------------------------------------------------------------------------
# Credentials (from the environment — never hardcode these)
# ---------------------------------------------------------------------------
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ===========================================================================
# PART 1 — YOUR SEARCH PROFILE
# This is the part to edit. See docs/CUSTOMIZATION.md for a guided walkthrough.
# ===========================================================================

# --- 1a. Which countries to search -----------------------------------------
# Keys are the labels used in alerts and logs; values are what gets sent to the
# Apify actor as the location string.
COUNTRIES = {"Qatar": "Qatar", "Saudi Arabia": "Saudi Arabia"}

# City/country words that prove a posting really is in each target country.
# A posting whose location matches none of these is rejected, because an
# unqualified "Remote" posting does not confirm the country.
# Lowercase only. Add your own cities when you change COUNTRIES.
COUNTRY_LOCATION_TERMS = {
    "Qatar": [
        "qatar", "doha", "al rayyan", "al wakrah", "lusail", "al khor", "umm salal",
    ],
    "Saudi Arabia": [
        "saudi arabia", "riyadh", "jeddah", "dammam", "dhahran", "khobar", "al khobar",
        "mecca", "makkah", "medina", "madinah", "tabuk", "abha", "jazan", "jubail",
    ],
}

# Locations that mean "this is somewhere else". A posting matching one of these
# is rejected unless it also matches the target country's terms above.
# Remove any country you actually want to target.
FOREIGN_LOCATION_TERMS = [
    "united arab emirates", "uae", "dubai", "abu dhabi", "kuwait", "bahrain", "oman",
    "united kingdom", "united states", "india",
]

# --- 1b. What to search for ------------------------------------------------
# These are the PAID searches. Each keyword runs against each country, so
# 4 keywords x 2 countries = 8 paid search combinations.
# Keep this list short and broad: narrowing happens locally and for free in
# relevance.py. Adding keywords here directly increases your Apify bill.
SEARCH_KEYWORDS = [
    "IT Support",
    "Technical Support",
    "Application Support",
    "Customer Support",
]

# --- 1c. When to run -------------------------------------------------------
# Timezone the schedule is expressed in. Gulf Standard Time (UTC+3) by default.
# Examples: timezone(timedelta(hours=5, minutes=30)) for IST,
#           timezone(timedelta(hours=0)) for UTC.
SCHEDULE_TZ = timezone(timedelta(hours=3))
GULF_TZ = SCHEDULE_TZ  # backwards-compatible alias used throughout main.py

# Weekdays the bot does NOT run, as Python weekday numbers
# (Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6).
# {4, 5} = Friday and Saturday off, which is the Gulf working week.
# Use {5, 6} for a Saturday/Sunday weekend.
NON_WORKING_WEEKDAYS = {4, 5}

# Hours (in SCHEDULE_TZ) at which a run is allowed. The systemd timer must be
# set to the matching times in UTC — see deploy/firstqueue.timer.
SCHEDULE_HOURS = {9: "09:00", 12: "12:00", 15: "15:00", 18: "18:00"}

# How many minutes past the hour a run is still accepted. This is what blocks
# systemd catch-up runs from firing at arbitrary times after a reboot.
SCHEDULE_HOUR_GRACE_MINUTES = 10

# Dates to skip, per country. Religious holidays move every year, so update
# these annually. Format: "YYYY-MM-DD".
PUBLIC_HOLIDAYS = {
    "Saudi Arabia": {"2026-02-22", "2026-09-23"},
    "Qatar": {"2026-02-22", "2026-12-18"},
}

# --- 1d. Spending limits ---------------------------------------------------
# Hard ceilings. The bot stops making paid searches before crossing them.
# READ docs/SETUP.md on cost before raising these — Apify's free tier is $5/month.
MAX_RESULTS_PER_COMBO = 150          # results requested per keyword/country search
MAX_COMBOS_PER_RUN = 4               # paid searches per run (rotates through the rest)
SAFETY_MAX_RESULTS_PER_RUN = 600     # 150 x 4
MAX_APIFY_COST_PER_RUN = 0.50        # US dollars
MAX_APIFY_COST_PER_DAY = 2.00        # US dollars, per UTC day

# --- 1e. How fresh a posting must be ---------------------------------------
MAX_JOB_AGE_HOURS = 24

# --- 1f. How strict the matching is ----------------------------------------
# Scores run 0-100. Raise the alert threshold to get fewer, better-matched
# alerts; lower it to see more.
RELEVANCE_ALERT_THRESHOLD = 55.0              # below this, no alert
RELEVANCE_HIGH_THRESHOLD = 78.0               # at or above this, labelled HIGH
RELEVANCE_OVERRIDE_NEGATIVE_THRESHOLD = 82.0  # score needed to survive a negative signal

# Free-text description of the roles you want. Only used by the optional
# embedding model (see 3c); the rule-based scoring ignores it.
RELEVANCE_QUERY = (
    "IT Support Technical Support Application Support Service Desk Help Desk "
    "Customer Support Saudi Arabia Qatar"
)


# ===========================================================================
# PART 2 — RELEVANCE VOCABULARY
# The words the local scoring engine looks for. Replace these wholesale if you
# are targeting a different profession. docs/CUSTOMIZATION.md has a prompt that
# will generate a replacement set for your own role.
# ===========================================================================

# Role families. A match here against the job TITLE is the strongest signal.
# NOC and Cloud Support Engineer are deliberately absent — they are adjacent
# roles this profile does not want.
ROLE_FAMILIES = {
    "IT Support": [
        "it support", "it support engineer", "it support specialist", "it support analyst",
        "desktop support", "desktop support engineer", "desktop support specialist",
        "infrastructure support", "infrastructure support engineer", "systems support",
        "systems support engineer", "systems support specialist", "it operations support",
    ],
    "Technical Support": [
        "technical support", "technical support engineer", "technical support specialist",
        "technical support analyst", "customer technical support", "technical support representative",
    ],
    "Application Support": [
        "application support", "application support engineer", "application support specialist",
        "application support analyst", "l2 application support", "l2 support", "l2 support engineer",
        "production support", "production support engineer", "production support analyst",
        "software support", "platform support", "application operations", "application operations support",
        "emr support", "healthcare it support",
    ],
    "Service Desk": [
        "service desk", "service desk engineer", "service desk analyst", "help desk", "help desk engineer",
        "help desk analyst", "helpdesk", "helpdesk engineer", "helpdesk analyst",
    ],
    "Customer Support": [
        "customer support", "customer support representative", "customer support specialist",
        "customer service", "customer service representative", "customer service agent",
        "technical customer support", "customer technical support",
    ],
}

ROLE_KEYWORDS = sorted({p for values in ROLE_FAMILIES.values() for p in values})
TITLE_ROLE_PATTERNS = ROLE_KEYWORDS + [
    "support analyst", "support specialist", "support engineer", "support representative", "support agent",
]
DESCRIPTION_ROLE_PATTERNS = [
    "technical support", "application support", "production support", "service desk", "help desk", "helpdesk",
    "desktop support", "incident management", "troubleshooting", "user support", "application operations",
    "system support", "it operations", "customer support", "customer service", "technical assistance",
]

# Tools and practices that confirm a posting is genuinely technical.
TECHNICAL_SIGNALS = [
    "sql", "api", "apis", "integration", "middleware", "smpp", "linux", "windows",
    "azure", "aws", "microsoft 365", "active directory", "dns", "dhcp", "vpn",
    "tcp/ip", "networking", "database", "oracle", "postgresql", "mysql", "powershell",
    "monitoring", "application availability", "incident management", "root cause analysis",
    "troubleshooting", "production environment", "ticketing", "itil", "sla", "service now", "servicenow",
]
SUPPORT_SIGNALS = [
    "customer support", "customer service", "end user support", "user support", "incident", "service request",
    "ticket", "helpdesk", "service desk", "technical assistance", "escalation", "sla", "first line", "second line",
    "l1", "l2",
]

# Titles that mean "this is not the job I want", however the description reads.
# A hit here applies a large penalty. Softer commercial terms such as
# "account manager" are handled separately inside relevance.py.
NEGATIVE_TITLE_TERMS = [
    "account executive", "sales executive", "sales manager", "sales representative", "sales specialist",
    "business development", "business development manager", "business development executive",
    "marketing manager", "marketing executive", "digital marketing", "recruiter", "recruitment consultant",
    "talent acquisition", "real estate", "insurance sales", "relationship manager", "commission sales",
]
NEGATIVE_DESCRIPTION_TERMS = [
    "commission based", "commission-based", "cold calling", "sales target", "sales quota",
    "lead generation", "business development", "real estate sales", "insurance sales",
]


# ===========================================================================
# PART 3 — OPERATIONAL TUNING
# Sensible defaults. You can usually leave all of this alone.
# ===========================================================================

# --- 3a. Apify ------------------------------------------------------------
# The LinkedIn jobs actor this project was built against. If you swap actors,
# check the input field names in fetch_jobs() in main.py and update
# APIFY_COST_PER_1000_RESULTS to the new actor's price.
APIFY_ACTOR_ID = "2rJKkhh7vjpX7pvjg"
APIFY_COST_PER_1000_RESULTS = 0.70
APIFY_RUN_TIMEOUT_SECS = 300

# Set to 1/true/yes to bypass the weekday, hour and holiday guards. Intended
# for a one-off manual test run, not for production.
IGNORE_SCHEDULE_GUARDS = os.environ.get("IGNORE_SCHEDULE_GUARDS", "").lower() in ("1", "true", "yes")

# --- 3b. Telegram delivery ------------------------------------------------
TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MIN_SEND_INTERVAL_SECS = 1.05
TELEGRAM_SEND_TIMEOUT_SECS = 10
TELEGRAM_MAX_RETRIES = 4
TELEGRAM_BACKOFF_SECS = 2
REQUIREMENTS_SUMMARY_MAX_CHARS = 450
# Ceiling on alerts per run, so an unexpected result spike cannot flood the chat.
# Jobs above the cap are not marked as alerted and stay eligible for a later run.
MAX_ALERTS_PER_RUN = 25

# --- 3c. Optional embedding model -----------------------------------------
# Off by default. The bot works fully without it; this adds a semantic
# similarity signal worth 20% of the final score. Needs ~90MB of model
# download and noticeably more RAM — check it fits your VPS first.
# Enable with ENABLE_EMBEDDING_MODEL=1 and pip install -r requirements-semantic.txt
ENABLE_EMBEDDING_MODEL = os.environ.get("ENABLE_EMBEDDING_MODEL", "0").lower() in ("1", "true", "yes")
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
EMBEDDING_TEXT_MAX_CHARS = 6000
EMBEDDING_STRONG_THRESHOLD = 78.0

# --- 3d. Result-volume anomaly detection ----------------------------------
# Compares each search's result count against its own recent median and warns
# on a large swing, which usually means the scraper or LinkedIn changed.
ANOMALY_MIN_HISTORY = 3
ANOMALY_RELATIVE_CHANGE = 0.50
ANOMALY_ZERO_FLOOR = 5
ANOMALY_LOOKBACK_RUNS = 20

# --- 3e. Application tracking ---------------------------------------------
# Statuses accepted by `python3 main.py --status <job_key> <STATUS>`.
APPLICATION_STATUSES = (
    "DISCOVERED", "ALERTED", "APPLIED", "SCREENING", "INTERVIEW", "OFFER", "REJECTED", "CLOSED"
)

# How many of the paid search combinations run per slot. The rest rotate in on
# the following run, so all combinations are covered without one oversized run.
SEARCH_ROTATION_SIZE = MAX_COMBOS_PER_RUN
