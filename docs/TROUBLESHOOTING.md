# Troubleshooting

## Read the run summary first

Almost every question is answered by the last line of a run:

```bash
cd ~/firstqueue
tail -40 bot.log
# or, when run by systemd:
sudo journalctl -u firstqueue.service -n 60 --no-pager
```

```
Run a1b2c3 finished 47.21s | fetched=287 matched=3 alerted=3 stale=201
unknown_date=12 wrong_location=48 duplicate=0 low_relevance=23 holiday=0 errors=0 cost=$0.2009
```

| Counter | Meaning | If it's unexpectedly high |
|---|---|---|
| `fetched` | postings Apify returned | `0` → the Apify call failed, see below |
| `stale` | older than `MAX_JOB_AGE_HOURS` | normal — most postings are old |
| `unknown_date` | no parseable posting date | normal in small numbers; if huge, the actor changed its date field |
| `wrong_location` | location didn't confirm the country | your `COUNTRY_LOCATION_TERMS` is missing cities |
| `duplicate` | already alerted | normal |
| `low_relevance` | scored below the threshold | if everything lands here, your vocabulary doesn't match reality |
| `matched` | passed every gate | this is what you care about |
| `alerted` | actually delivered | should equal `matched` minus duplicates |

---

## No alerts at all

### 1. Is it even running?

```bash
systemctl list-timers firstqueue.timer
sudo journalctl -u firstqueue.service -n 30 --no-pager
```

No entries at all → the timer isn't enabled:

```bash
sudo systemctl enable --now firstqueue.timer
```

### 2. `skipped: outside scheduled Gulf hour`

**The most common problem.** Your systemd timer and `config.py` disagree.

The timer is UTC; `SCHEDULE_HOURS` is in `SCHEDULE_TZ`. The bot refuses to run at an hour `config.py` doesn't list, so a mismatched timer produces a run that exits immediately.

```bash
grep -E "SCHEDULE_HOURS|SCHEDULE_TZ" config.py
grep OnCalendar /etc/systemd/system/firstqueue.timer
```

Local hour minus UTC offset = the UTC hour for the timer. Gulf (UTC+3) 09:00 → 06:00 UTC. See [CUSTOMIZATION.md §3](CUSTOMIZATION.md#3-change-the-schedule).

### 3. `skipped: Gulf weekend` / `weekend (Saturday)`

`NON_WORKING_WEEKDAYS` is `{4, 5}` by default — Friday and Saturday off. For a Sat/Sun weekend use `{5, 6}`. Mon=0 … Sun=6.

### 4. `Missing environment variables`

The `.env` file isn't reaching the process.

```bash
sudo systemctl cat firstqueue.service | grep EnvironmentFile   # path correct?
ls -l ~/firstqueue/.env                                          # file exists?
grep -c . ~/firstqueue/.env                                      # values filled in?
```

systemd's `EnvironmentFile` needs plain `KEY=value` — no `export`, no spaces around `=`, no surrounding quotes.

Testing by hand needs the variables loaded into your shell first:

```bash
set -a && source .env && set +a
IGNORE_SCHEDULE_GUARDS=1 python3 main.py
```

### 5. `fetched=0` — Apify returned nothing

```bash
set -a && source .env && set +a
python3 -c "
from apify_client import ApifyClient
import config
c = ApifyClient(config.APIFY_API_TOKEN)
print(c.user('me').get()['username'])
"
```

- **Auth error** → bad or revoked `APIFY_API_TOKEN`.
- **Works, but still no results** → check your Apify console. Out of credit? The actor erroring or deprecated? Open the actor's last run there and read its log.
- **Everything looks fine** → the actor may have changed its input field names. Compare `fetch_jobs()` in `main.py` against the actor's current input schema.

### 6. Everything lands in `low_relevance`

Your vocabulary doesn't match how postings are actually written. Test a real title:

```bash
python3 -c "
import relevance, json
print(json.dumps(relevance.score_job(
  'PASTE A REAL JOB TITLE HERE',
  'paste part of its description here'), indent=2))
"
```

The `reasons` and `negative_reasons` arrays tell you exactly what did and didn't fire. Usually the fix is adding title variants to `ROLE_FAMILIES`, not lowering the threshold.

### 7. Everything lands in `wrong_location`

`COUNTRY_LOCATION_TERMS` is missing cities, or your target country is still sitting in `FOREIGN_LOCATION_TERMS`.

```bash
python3 -c "
import main
print(main.validate_location('Dubai, United Arab Emirates', 'United Arab Emirates'))
"
```

Returns `(False, ...)` → add the missing terms. Note that a bare `"Remote"` is rejected on purpose: it doesn't prove the country.

---

## Telegram problems

### Nothing arrives, but the log says `ALERT SENT`

The bot got a success from Telegram, so the message went somewhere — almost certainly the wrong chat.

```bash
grep TELEGRAM_CHAT_ID .env    # a number, not a @username?
```

Re-check it via `https://api.telegram.org/bot<TOKEN>/getUpdates` after messaging your bot.

### `Telegram permanent failure: 400`

- `chat not found` → wrong chat ID, or you never pressed **Start** on the bot. Bots can't initiate conversations.
- `can't parse entities` → a job title contains characters breaking the HTML parse. `escape_html()` handles this; if you edited `build_alert()`, make sure every interpolated value goes through it.

### `Telegram permanent failure: 401`

Wrong or revoked bot token. Regenerate it with `/token` in @BotFather.

### Repeated `Telegram 429`

Rate limiting. Already handled — the bot waits for the server's `retry_after` and retries. If it's constant, lower `MAX_ALERTS_PER_RUN`.

---

## Duplicate alerts for the same job

Shouldn't happen — dedup runs on the LinkedIn numeric ID with a canonical-URL fallback. If it does:

```bash
sqlite3 jobs.db "SELECT job_key, title, url FROM jobs ORDER BY alerted_at DESC LIMIT 10;"
```

Two `scraper:*` keys for the same posting means the actor returned no usable LinkedIn job ID and changed its own ID between runs. Check whether the URLs differ — if they carry different tracking parameters that `normalize_url()` doesn't strip, add them to the `removable` set in `main.py`.

---

## "Job bot search-volume warning" messages

The anomaly detector working as intended: a search returned a count far from its own rolling median, or zero when it usually returns results.

Common causes, in order of likelihood: it's a genuinely quiet day; the actor changed or broke; your Apify credit ran out; LinkedIn changed something.

Check the Apify console first. To make the warnings less sensitive:

```python
ANOMALY_RELATIVE_CHANGE = 0.75   # was 0.50 — tolerate bigger swings
```

---

## Cost problems

### Burning through credit faster than expected

```bash
sqlite3 jobs.db "SELECT date(timestamp) day, ROUND(SUM(apify_cost_estimate),4) usd
                 FROM run_history WHERE keyword!='__RUN_TOTAL__'
                 GROUP BY day ORDER BY day DESC LIMIT 14;"
```

Compare against the real number in the Apify console. **If they disagree, the actor's price changed** — update `APIFY_COST_PER_1000_RESULTS` in `config.py`, because every spending guard is computed from it and they're all currently wrong.

Then cut usage: fewer `SCHEDULE_HOURS`, lower `MAX_RESULTS_PER_COMBO`, fewer `SEARCH_KEYWORDS`. See the [cost table](SETUP.md#7-cost-control).

### `Per-run cost guard reached` in the logs

Working as designed — it stopped before overspending. The remaining searches rotate into the next run, so coverage isn't lost. If it fires every run, your `MAX_APIFY_COST_PER_RUN` is lower than one full rotation costs.

---

## Installation and runtime errors

### `ModuleNotFoundError: No module named 'apify_client'`

The virtualenv isn't active, or systemd is using the system Python.

```bash
source venv/bin/activate && pip install -r requirements.txt
# and check the service points at the venv python:
grep ExecStart /etc/systemd/system/firstqueue.service
```

It must point to your FirstQueue virtualenv, for example `/home/YOUR_LINUX_USERNAME/firstqueue/venv/bin/python3`, not `/usr/bin/python3`.

### `requests==2.33.0` won't install

Needs **Python 3.10+**.

```bash
python3 --version
```

On an older Ubuntu, either upgrade the OS or install a newer Python. Don't pin `requests` back to 2.32.4 — that version carries CVE-2026-25645, which is why it's pinned forward.

### `database is locked`

Two runs overlapping. WAL mode and a 30-second busy timeout are already set, so this normally resolves itself.

```bash
systemctl list-timers firstqueue.timer   # duplicate timers?
ps aux | grep main.py                        # a stuck process?
```

### `sentence-transformers` won't install

Expected on ARM and on Python versions it doesn't have wheels for. It's **optional** — leave `ENABLE_EMBEDDING_MODEL=0` and everything else works. It also wants ~300MB more RAM than a 1GB free VM comfortably has.

---

## Useful queries

```bash
# Recent alerts
sqlite3 jobs.db "SELECT alerted_at, relevance_score, title, company
                 FROM jobs ORDER BY alerted_at DESC LIMIT 20;"

# Where postings are being dropped, per search
sqlite3 jobs.db "SELECT keyword, country, SUM(jobs_fetched) fetched, SUM(jobs_alerted) alerted,
                 SUM(skipped_low_relevance) low_rel, SUM(skipped_wrong_location) wrong_loc
                 FROM run_history WHERE keyword!='__RUN_TOTAL__'
                 GROUP BY keyword, country;"

# Application pipeline
sqlite3 jobs.db "SELECT alert_status, COUNT(*) FROM jobs GROUP BY alert_status;"

# History for one job
sqlite3 jobs.db "SELECT changed_at, old_status, new_status, note
                 FROM application_events WHERE job_key='linkedin:123456789'
                 ORDER BY changed_at;"
```

---

## Starting over

Keeping credentials and config, discarding history:

```bash
sudo systemctl stop firstqueue.timer
mv jobs.db jobs.db.old          # keep a copy rather than deleting
sudo systemctl start firstqueue.timer
```

A fresh database means previously-alerted jobs can alert again if they're still inside the 24-hour window.

---

## Still stuck?

Open an issue with:

- the run summary line from `bot.log`
- your `config.py` **Part 1** (it holds no secrets — but double-check before pasting)
- `python3 --version` and your OS
- what you expected versus what happened

**Never paste your `.env`, tokens, or chat ID into an issue.**
