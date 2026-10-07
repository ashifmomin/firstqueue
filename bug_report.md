---
name: Bug report
about: Something isn't working
title: ''
labels: bug
---

<!--
NEVER paste your .env, APIFY_API_TOKEN, TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.
Check anything you paste for those first.
-->

**What happened**

**What you expected**

**Run summary line** (from `bot.log` or `journalctl -u firstqueue.service`)

```
Run ... finished ...s | fetched= matched= alerted= stale= unknown_date= wrong_location= duplicate= low_relevance= holiday= errors= cost=$
```

**Relevant log lines**

```
```

**Environment**
- Python version (`python3 --version`):
- OS:
- Running via systemd or manually:
- Default config, or retargeted to another role/country:

**config.py Part 1** (optional — check it for anything personal first)

```python
```

**Already tried**
- [ ] `python3 -m unittest tests.py` passes
- [ ] Checked [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md)
- [ ] systemd timer times match `SCHEDULE_HOURS` in `config.py`
