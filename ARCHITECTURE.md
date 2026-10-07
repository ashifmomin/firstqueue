# Architecture

Three modules, one SQLite database, no server process. systemd runs `main.py`, it works for a minute or two, and exits.

```
config.py      all settings and vocabulary
relevance.py   scoring — pure functions, no I/O
main.py        pipeline, filters, Telegram, database
jobs.db        dedup history, run metrics, application tracking
```

`relevance.py` imports `config` and nothing else, which is why you can score a title from a one-line `python3 -c` without touching the network or the database.

---

## The pipeline

```
main()
 ├── setup_logging()                 rotating file + stdout
 ├── init_db()                       create/migrate schema
 ├── credential check                abort if tokens missing
 ├── config sanity check             abort if a country has no location terms
 ├── schedule_block_reason()         abort if wrong day/hour/minute
 └── for each of 4 rotating searches:
      ├── country_holiday()          skip this country today?
      ├── cost guards                stop BEFORE spending over a limit
      ├── fetch_jobs()               ← the only paid call
      ├── historical_anomaly()       result count vs own rolling median
      └── for each posting:
           ├── extract_job()         normalize fields, build job_key
           ├── date gate             unknown / >24h / future → drop
           ├── validate_location()   must confirm the target country
           ├── score_job()           0-100 + reasons
           ├── should_alert()        threshold + negative override
           └── already_alerted()     dedup against the database
      ├── sort by score, cap at MAX_ALERTS_PER_RUN
      └── for each surviving job:
           ├── telegram.send()       retries 429/5xx/network
           └── record_job()          ONLY after delivery succeeds
```

### Why the order matters

The gates run cheapest-first. Date and location are string checks that eliminate most postings before scoring runs. Scoring happens before the dedup query so the database isn't hit for jobs that would never alert anyway.

**Cost guards run before `fetch_jobs()`, not after.** Each iteration estimates what the next search would cost and breaks out if it would cross a ceiling. A guard that triggered after the call would already have spent the money.

**`record_job()` runs only after Telegram confirms delivery.** A failed send leaves the job unrecorded, so the next run treats it as new and retries. The alternative — record then send — loses jobs permanently on a transient network error.

---

## Search rotation

8 paid combinations (4 keywords × 2 countries), 4 per run. A cursor in the `bot_state` table advances after each search, so two consecutive runs cover all 8.

```python
cursor = int(get_state(conn, "search_rotation_cursor", "0")) % len(combos)
return [combos[(cursor + i) % len(combos)] for i in range(min(SEARCH_ROTATION_SIZE, len(combos)))]
```

Because the cursor is in the database rather than memory, coverage survives restarts and crashes. Replacing an earlier design that attempted all 8 in one run and hit a 300-result stop condition before finishing — which meant the last combinations were never searched at all.

---

## Relevance scoring

`score_job(title, description)` returns a score, a band, and the reasons for both. Deterministic and auditable: the same input always produces the same output, and every point is attributable.

### Points

| Signal | Points | Note |
|---|---|---|
| Role family in **title** | **+45** | the strongest signal |
| More than one family matched | +4 | |
| Generic support title (no family) | +32 | "Support Engineer" with no family hit |
| Exact role phrase in title | +25 | |
| Exact role phrase in description only | +7 | deliberately much weaker |
| Technical signals | +2.5 each, **max 17** | |
| Support signals | +2.0 each, **max 12** | |
| Description-only role language | +7 to +15 | only when the title gave nothing |
| Fuzzy title similarity ≥0.78 | +10 | catches "Application Support (L2)" |
| Fuzzy title similarity ≥0.64 | +5 | |
| **Negative title term** | **−42 each**, max −80 | |
| Negative description term | −7 each, max −28 | |
| Soft commercial title | −18 each, max −35 | only when no family matched |

Clamped to 0–100. Bands: HIGH ≥78, MEDIUM ≥55, LOW below.

### The title/description asymmetry

A role phrase in the title scores 25; the same phrase in the description scores 7. This is the design's central judgement. Job descriptions mention "customer support" constantly — in the duties of a sales role, in boilerplate about the company's values. Titles are a far more honest signal of what the job is.

It's also why a "Software Engineer" whose description mentions providing technical support scores materially below an actual "Technical Support Engineer".

### Negative suppression

A negative title term costs 42 points — enough that a 45-point family match can't carry a sales title over the threshold on its own. And `should_alert()` adds a second gate:

```python
if result["negative_reasons"] and result["score"] < RELEVANCE_OVERRIDE_NEGATIVE_THRESHOLD:
    return False
```

So a job with any negative signal needs 82+, not 55, to alert. A genuinely strong technical-support title with one unfortunate word can still get through; an Account Executive with a support-heavy description cannot.

Soft commercial terms ("account manager", "customer success") are penalised *only when no role family matched* — otherwise "Customer Success Support Engineer" would be wrongly suppressed.

### Normalization

`normalize_text()` runs before every comparison: lowercase, `&` → `and`, dashes and slashes → spaces, `help desk`/`helpdesk` collapsed, whitespace squeezed. This is why "Help Desk Analyst" and "Helpdesk Analyst" score within 1 point of each other — a test asserts it.

### The optional embedding layer

With `ENABLE_EMBEDDING_MODEL=1`, a sentence-transformers model scores query/document similarity and is blended in at 20%:

```python
score = (score * 0.80) + (embedding_score * 0.20)
```

The model is cached on the function object after first load. Every failure path — import error, download failure, encode error — returns `None` and the rule-based score stands alone. **The feature cannot break the bot**, which is why it ships off by default.

---

## Hard gates

Three filters that run before scoring and can't be overridden by a high score.

**Freshness.** `parse_posted_at()` handles epoch seconds, epoch milliseconds, ISO 8601, and relative strings ("3 hours ago", "just now"). Anything unparseable returns `None` and the posting is **rejected**, not assumed recent — an unknown date is more likely to be an old posting than a new one. Future-dated postings beyond a 5-minute tolerance are also rejected.

**Location.** The location text must contain one of the target country's configured terms. A bare `"Remote"` or `"Hybrid"` is rejected because it doesn't confirm the country; `"Remote - Riyadh, Saudi Arabia"` is accepted. An explicit foreign location is rejected unless it also matches a target term.

**Deduplication.** `job_key` prefers the stable numeric LinkedIn job ID extracted from the URL, falls back to the scraper's own ID, then to a canonical URL. The dedup query checks `job_key` *and* `url`, so a database written under an older keying scheme stays useful. `normalize_url()` strips `trk`, `trackingId`, `refId`, `lipi`, `utm_*`, `fbclid` and friends, lowercases the host, and trims the trailing slash.

Preferring the LinkedIn ID matters because scraper IDs aren't stable between runs — the same posting can come back with a different scraper ID and would otherwise alert twice.

---

## Schedule guards

Two independent mechanisms, and both must agree:

1. **systemd timer** — fires at fixed UTC times.
2. **`schedule_block_reason()`** — the bot's own check: not a non-working weekday, hour in `SCHEDULE_HOURS`, minute within `SCHEDULE_HOUR_GRACE_MINUTES`.

The second exists because `Persistent=true` is on. After a reboot, systemd wants to run missed timers immediately — which could mean a paid run at 3am. The minute-window guard refuses, logs why, and records a skipped run.

This is the most common configuration mistake: a timer that doesn't line up with `SCHEDULE_HOURS` produces runs that always exit immediately.

Holidays are checked per country inside the search loop, not globally, so a Saudi holiday doesn't block the Qatar searches.

---

## Database

```sql
jobs                -- one row per alerted job (dedup + current status)
run_history         -- one row per search, plus a __RUN_TOTAL__ summary row
bot_state           -- key/value; holds the rotation cursor
application_events  -- append-only status transition log
```

**Migration.** `init_db()` uses `CREATE TABLE IF NOT EXISTS`, then `_add_missing_columns()` adds any new columns in place. Upgrading never requires deleting `jobs.db` — a test creates an old-schema database, migrates it, and asserts the old rows survive.

`_add_missing_columns()` takes its table name from an allowlist:

```python
_ALLOWED_MIGRATION_TABLES = {"jobs", "run_history"}
```

Table names can't be parameterised in SQL, so they're interpolated — and the allowlist is what makes that safe. A test asserts `"jobs; DROP TABLE jobs; --"` raises.

**WAL mode** and a 30-second busy timeout are set at connect, so a reader and a writer don't block each other.

**`run_history` carries two kinds of row:** per-search rows, and one summary row per run with `keyword='__RUN_TOTAL__'`. Every aggregate query must exclude the sentinel or costs double-count. The cost queries in the docs all do.

---

## Logging and security

Rotating file handler, 2MB × 5 backups (~12MB ceiling), plus stdout so `journalctl` captures everything.

Untrusted LinkedIn text — titles, company names, URLs — passes through `_sanitize_log()` before being logged:

```python
def _sanitize_log(value: Any) -> str:
    return re.sub(r"[\r\n]+", " ", str(value))
```

Without it, a job title containing `\n2026-01-01 00:00:00 | INFO | ...` would write a forged log line (CWE-117, log injection). Found by security-testing this project against itself, fixed, and covered by a regression test.

Telegram messages pass every interpolated value through `escape_html()`, so a title containing `<` can't break the HTML parse or inject markup.

---

## Failure handling

| Failure | Response |
|---|---|
| One search raises | caught per search; others continue; Telegram error notice |
| Telegram 429 | wait the server's `retry_after`, retry (4 attempts) |
| Telegram 5xx | linear backoff, retry |
| Telegram network error | linear backoff, retry |
| Telegram permanent failure | job left unrecorded so a later run retries |
| Unhandled crash | logged, Telegram crash notice, exit 1 |
| Crash notice itself fails | logged explicitly — never a bare `except: pass` |

The design principle: **silence means "nothing matched", never "it died".** Every failure mode either retries or tells you.

---

## Deliberate non-features

- **LinkedIn only.** No other job sources. Scope decision, not a gap.
- **No auto-apply.** Discovery and filtering only.
- **No web UI.** Telegram is the interface; SQLite is the data layer.
- **No LLM in the scoring path.** Rules are free, deterministic and auditable. The optional embedding model is local, and off by default.
