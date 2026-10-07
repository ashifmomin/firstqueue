# Changelog

Notable changes to FirstQueue. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased] — open-source release preparation

### Added
- `README.md`, plus `docs/SETUP.md`, `docs/CUSTOMIZATION.md`, `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md` and `docs/QA.md`.
- `.env.example` as a credential template, and `.gitignore` covering `.env`, `jobs.db` and `bot.log`.
- MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`.
- GitHub Actions workflow running the test suite on Python 3.10–3.13.
- `COUNTRY_LOCATION_TERMS` and `FOREIGN_LOCATION_TERMS` in `config.py`, so retargeting to a new country no longer requires editing `main.py`.
- Startup check that aborts with a clear message if a country in `COUNTRIES` has no entry in `COUNTRY_LOCATION_TERMS` — previously this silently rejected every posting.
- `SCHEDULE_TZ` as the documented name for the schedule timezone (`GULF_TZ` kept as an alias).

### Changed
- `config.py` reorganised into three parts — your search profile, the relevance vocabulary, and operational tuning — so the settings worth editing are together at the top.
- `validate_location()` now reads its city and country vocabulary from `config.py` instead of hardcoded lists.

### Security
- No credentials were ever committed. All three secrets are read from the environment.

---

## [v0.1-security] — Security hardening

### Fixed
- **Log injection (CWE-117).** LinkedIn-sourced job title, company and URL values are sanitized before being written to logs, so a crafted job title can no longer forge log entries.
- `_add_missing_columns()` now validates migration table names against an allowlist (`jobs`, `run_history`).
- Replaced a bare exception handler in the fatal-notification path with an explicit `Exception` handler plus a diagnostic log entry — a failed crash notification is no longer silent.

### Changed
- `requests` upgraded 2.32.4 → 2.33.0 for CVE-2026-25645. **This raises the minimum runtime to Python 3.10+**; a Python 3.8 virtualenv must be upgraded before deploying.

### Added
- Regression tests for CR/LF log sanitization.
- A migration-table allowlist rejection test.
- A test confirming allowed migration tables still migrate correctly.

---

## [v1.38]

### Added — search coverage
- Persistent 4-of-8 search rotation via the SQLite `bot_state` table; all eight keyword/country combinations are covered across two scheduled runs.

### Fixed — search coverage
- Removed the 300-result stop condition that prevented later keyword/country combinations from ever being searched.

### Added — relevance
- Role-family classification.
- Customer Support / Customer Service family.
- Softer treatment of ambiguous commercial titles.

### Changed — relevance
- Normalized Help Desk / Helpdesk to the same family.
- Improved bare `IT Support` handling.
- Removed NOC / NOC Support from the target role vocabulary; NOC Engineer and Cloud Support Engineer are explicitly rejected in regression tests.
- Cloud technologies (Azure, AWS) now count as technical context only — the cloud-support role itself is not a target.

### Added — freshness and location
- Reject unknown dates.
- Reject postings more than 24 hours old.
- Reject future-dated postings beyond a five-minute tolerance.
- Reject country-unspecified remote/hybrid postings.
- Apply public holidays per country rather than globally.

### Added — deduplication
- Prefer the numeric LinkedIn job ID over scraper IDs.
- Check existing records by job key *or* canonical URL.

### Added — cost and reliability
- Per-run and per-day dollar cost guards.
- Historical median-based result-volume anomaly detection, replacing a fixed 100-result threshold.
- Retained Telegram 429/5xx/network retry logic.

### Added — alerts
- Rank eligible jobs by relevance before Telegram delivery.
- Per-run alert cap to protect against unexpected result spikes.
- Extract experience, salary, shift, Arabic and visa/relocation signals for the alert message.

### Added — application tracking
- `application_events` table preserving every status transition, instead of only the current state.

### QA
- Substantially expanded regression coverage. No external job sources added.

---

## [Semantic V2]

### Added
- `relevance.py` — local relevance-ranking engine.
- Role-family expansion without increasing paid Apify searches.
- Title-first weighting.
- Exact-role phrase bonus.
- Technical/support signal scoring.
- Fuzzy title similarity.
- Negative-role suppression.
- Optional sentence-transformers embedding layer.
- 0–100 score with HIGH/MEDIUM/LOW band in Telegram alerts.
- Explainable match reasons in alerts.
- Unknown-date hard rejection.
- Actual location validation.
- LinkedIn job-ID extraction and URL canonicalization.
- Telegram retry handling for 429, 5xx and network errors.
- Exact scheduled-hour guard.
- SQLite WAL mode, busy timeout and in-place schema migration.
- Relevance/location/date/anomaly counters in `run_history`.
- Application lifecycle status updates.
- 17 automated regression tests.

### Deliberately not implemented
Bayt, GulfTalent, Naukrigulf, Indeed, Glassdoor, company career pages. The source remains LinkedIn-only through the existing Apify actor.

### Note on terminology
This is **not** LinkedIn's proprietary ranking model. LinkedIn's published engineering material describes a far larger LLM/embedding retrieval and ranking system. FirstQueue implements a smaller, explainable local ranking layer with an optional embedding model, to improve relevance while keeping a low-cost VPS architecture.
