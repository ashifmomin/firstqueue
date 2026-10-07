# FirstQueue

**A self-hosted job alert bot. It checks LinkedIn on a schedule, filters out everything irrelevant, and sends only the jobs worth your attention to Telegram — usually within hours of posting.**

Built because job boards are noisy: searching "IT Support, Qatar" returns sales roles, recruiter spam, jobs posted three weeks ago, and the same posting four times. FirstQueue does that filtering for you, on a timer, and messages you when something real shows up.

Default configuration targets **IT support roles in Qatar and Saudi Arabia**, because that's what it was built for. It's designed to be retargeted — see [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md).

[![Tests](https://github.com/ashifmomin/firstqueue/actions/workflows/tests.yml/badge.svg)](https://github.com/ashifmomin/firstqueue/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it actually does

```
Scheduled run (4x per working day)
        ↓
Apify LinkedIn actor — 4 of 8 paid searches, rotating
        ↓
Hard gates:   posted < 24h ago
              location confirms the target country
              not already sent
        ↓
Relevance scoring (local, free, explainable)  →  0-100 + HIGH/MEDIUM/LOW
        ↓
Telegram alert, ranked best-first, with the reasons it matched
        ↓
SQLite — dedup history + application tracking
```

Each alert tells you the score, which role family matched, why it matched, how old the posting is, and what the posting says about experience, shift pattern, Arabic requirements and visa sponsorship — so you can decide whether to apply without opening the link.

## Features

**Relevance that explains itself.** A deterministic scoring engine in [`relevance.py`](relevance.py) — no LLM, no API cost, no black box. Title matches count more than description mentions. Sales and recruitment titles get suppressed even when their descriptions are stuffed with the word "support". Every score comes with the reasons behind it, so when it gets something wrong you can see why and fix the vocabulary.

**It won't surprise you with a bill.** Per-run and per-day dollar ceilings, a result-count ceiling, and a rotation that spreads 8 searches across 2 runs instead of one oversized run. The bot stops making paid calls before crossing a limit rather than after.

**It respects a working week.** Sunday–Thursday, four slots a day, public holidays off, per country. It also refuses to run outside its scheduled minute window, so a server reboot can't trigger a surprise catch-up run at 3am.

**No duplicate alerts.** Deduplicates on the stable numeric LinkedIn job ID where available, falling back to a canonical URL with tracking parameters stripped — so the same job shared three different ways still only pings you once.

**Reliable delivery.** Telegram 429s are retried using the server's own `retry_after`, 5xx and network errors get backoff. A job is only recorded as sent after Telegram confirms delivery, so a failed send is retried on the next run instead of being lost.

**Tells you when it breaks.** Result volumes are compared against each search's own rolling median; an unexpected swing or zero-result run gets flagged to your Telegram. Crashes notify you too. Silence means "nothing matched", not "it died three weeks ago".

**Application tracking.** `DISCOVERED → ALERTED → APPLIED → SCREENING → INTERVIEW → OFFER`, with full event history, updated from the command line.

**Tested.** 34 tests covering relevance scoring, false-positive suppression, date and location gates, search rotation, schedule guards, holidays, database migration, anomaly detection, and the log-injection fix.

## What it does not do

Being direct about this, because job-automation tools tend to overpromise:

- **It does not apply to jobs for you.** It finds and filters postings. You apply.
- **It does not get you in first.** It alerts you fast, which helps. It cannot promise you'll be early, and the postings it finds already have other applicants.
- **It only reads LinkedIn.** No Bayt, GulfTalent, Naukrigulf, Indeed, Glassdoor, or company career pages. That's a deliberate scope decision, not a missing feature.
- **It doesn't scrape LinkedIn itself.** Retrieval goes through a third-party [Apify](https://apify.com) actor. You need an Apify account, and that part isn't free beyond their monthly credit.
- **There is no AI writing your applications.** The relevance engine is rules and string matching. The optional embedding model adds semantic similarity and nothing else.

## Requirements

| What | Why | Cost |
|---|---|---|
| Linux server, always on | runs on a timer | **Free** — Oracle Cloud Always Free tier works well |
| Python 3.10+ | required by `requests==2.33.0` | Free |
| [Apify](https://apify.com) account | LinkedIn job retrieval | **$5/month free credit**, then pay-per-use |
| Telegram account | where alerts arrive | Free |

**Apify cost is the one real expense.** The actor charges roughly **$0.70 per 1,000 results returned**. A realistic run returning ~300 results across 4 searches costs about **$0.20**. At 4 runs a day that's **$0.60–0.80/day**, which will exhaust the $5 monthly credit in about a week.

To stay inside the free credit, reduce `SCHEDULE_HOURS` to one or two runs a day and lower `MAX_RESULTS_PER_COMBO`. [docs/SETUP.md](docs/SETUP.md#cost-control) has a worked table of configurations and what each costs.

## Quick start

```bash
# 1. Get the code
git clone https://github.com/ashifmomin/firstqueue.git
cd firstqueue

# 2. Install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Add your credentials
cp .env.example .env
chmod 600 .env
nano .env          # fill in the three values

# 4. Confirm it works
python3 -m unittest tests.py

# 5. One manual test run (bypasses the schedule guards)
set -a && source .env && set +a
IGNORE_SCHEDULE_GUARDS=1 python3 main.py
```

That last command makes real Apify and Telegram calls and costs real Apify credit. If it works, you'll get Telegram messages.

Then install the timer so it runs on its own — [docs/SETUP.md](docs/SETUP.md) covers getting a free Oracle VPS, creating the Apify and Telegram credentials, and the systemd setup, step by step from nothing.

## Making it yours

The defaults look for IT support roles in Qatar and Saudi Arabia on a Gulf working week. To point it at your own role, country and schedule, edit **Part 1** of [`config.py`](config.py) — it's organised so the things you'll want to change are all at the top.

[docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) walks through each setting, and includes a **ready-to-paste AI prompt** that will generate a complete replacement vocabulary for your own profession — nursing, accounting, DevOps, whatever — so you don't have to write out the role families by hand.

## Documentation

| Document | What's in it |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Full setup from zero: free Oracle VPS, Apify, Telegram, systemd, cost control |
| [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) | Change the role, country, schedule and strictness — plus the AI prompt |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pipeline, scoring and database work |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | No alerts, wrong jobs, Telegram errors, timer not firing |
| [docs/QA.md](docs/QA.md) | Test specification and acceptance criteria |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SECURITY.md](SECURITY.md) | Credential handling and how to report a vulnerability |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to work on this |

## Project layout

```
firstqueue/
├── main.py                   # pipeline, scheduling, Telegram, database
├── relevance.py              # the scoring engine
├── config.py                 # all settings (Part 1 is the part you edit)
├── tests.py                  # 34 tests
├── requirements.txt          # two dependencies
├── requirements-semantic.txt # optional embedding model
├── .env.example              # credential template
├── deploy/                   # systemd service and timer
└── docs/
```

## Security

Credentials are read from the environment and never written to a tracked file. `.env`, `jobs.db` and `bot.log` are all gitignored — the database and log contain your personal search history.

The project has been security-tested against itself. A log-injection issue (CWE-117) in untrusted LinkedIn field handling was found and fixed with a sanitizer plus regression tests; the migration helper takes table names from an allowlist only. See [SECURITY.md](SECURITY.md) and the [security changelog entry](CHANGELOG.md).

## Contributing

Issues and pull requests are welcome. If you retarget it to a different profession or country and it works, a PR adding your vocabulary as an example profile would genuinely help other people. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE). Use it, change it, run it for yourself.

---

**A note on scraping:** retrieval runs through a third-party Apify actor, not direct LinkedIn scraping, but automated collection of LinkedIn data may still conflict with LinkedIn's Terms of Service. You are responsible for your own use of this tool. It's built for one person monitoring their own job search, at low volume, on a schedule — not for bulk data collection or resale.
