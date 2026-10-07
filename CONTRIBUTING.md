# Contributing

Thanks for looking. This is a small, deliberately narrow project — contributions are welcome, but it helps to know what's in scope before you start work.

## What's wanted

**Example profiles for other professions.** The highest-value contribution. If you retargeted FirstQueue to nursing, accounting, DevOps, teaching — anything — and it works well, a PR adding your vocabulary as an example profile saves the next person hours. See [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md).

**Relevance improvements.** Better scoring, fewer false positives. Must come with tests showing the before/after behaviour.

**Country location vocabulary.** More countries and cities for `COUNTRY_LOCATION_TERMS`.

**Documentation fixes.** Anything that didn't work as written when you followed it, especially in the setup guide. If you got stuck, someone else will too.

**Bug fixes.** With a regression test.

**Support for other Apify actors.** The actor input mapping is currently hardcoded in `fetch_jobs()`. A clean way to support alternatives would be useful.

## What's not wanted

These are deliberate scope decisions, not oversights:

- **Other job boards.** No Bayt, GulfTalent, Naukrigulf, Indeed, Glassdoor, or company career pages. LinkedIn-only keeps the project small and the cost model predictable.
- **Auto-apply.** FirstQueue finds and filters jobs. It will not submit applications.
- **A web UI or dashboard.** Telegram is the interface.
- **An LLM in the scoring path.** The relevance engine is deliberately rule-based: free, deterministic, and auditable. The optional embedding model is as far as this goes.
- **CV/résumé generation, interview prep, outreach automation.** Different projects.

If you want one of those, forking is completely reasonable — that's what the MIT licence is for.

---

## Working on it

```bash
git clone https://github.com/ashifmomin/firstqueue.git
cd firstqueue
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python3 -m unittest tests.py      # expect 34 passing
```

No credentials are needed to run the tests — `tests.py` stubs `apify_client` and makes no network calls.

### Before opening a PR

```bash
python3 -m py_compile main.py config.py relevance.py tests.py
python3 -m unittest -v tests.py
```

Both must pass. CI runs the same thing on Python 3.10–3.13.

### Code style

Match what's there. The existing code is plain, dependency-light Python:

- Type hints on function signatures.
- `from __future__ import annotations` at the top of each module.
- Comments explain *why*, not *what*. The existing comments are a good guide — `# NOC and Cloud Support Engineer are intentionally excluded` records a decision, which is the kind worth writing.
- No new runtime dependencies without a strong reason. Two is a feature.
- Settings go in `config.py`, never hardcoded in `main.py`. If you add a tunable value, put it in the right Part and document it.

### Tests

Any behaviour change needs a test. For a bug fix, write the test that fails first.

New tests go in the matching class in `tests.py`: `RelevanceTests`, `DateTests`, `UrlLocationTests`, `SearchRotationTests`, `ScheduleTests`, `MigrationTests`, `SecurityHardeningTests`, `AnomalyTests`.

Tests must not make network calls or need credentials.

### Pull requests

- One concern per PR.
- Say what you changed and why.
- For relevance changes, show the effect: which titles now score differently, and by how much.
- Update the docs if behaviour changed.
- Add a `CHANGELOG.md` entry under `[Unreleased]`.

---

## Reporting bugs

Include:

- the run summary line from `bot.log`
- `config.py` **Part 1** — check it for anything personal before pasting
- `python3 --version` and your OS
- expected vs actual

**Never paste your `.env`, API tokens, bot token or chat ID.** See [SECURITY.md](SECURITY.md).

For something security-sensitive, use GitHub's private vulnerability reporting instead of an issue.

---

## A note on expectations

This is maintained by one person alongside a full-time job. Reviews may take a week or two. A PR might be declined because it's out of scope rather than because it's bad work — checking the scope list above, or opening an issue first for anything substantial, saves everyone's time.
