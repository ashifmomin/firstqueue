# QA specification

The acceptance criteria the test suite enforces. Run it with:

```bash
python3 -m py_compile main.py config.py relevance.py tests.py
python3 -m unittest -v tests.py
```

34 tests. All must pass before a release.

> These criteria describe the **default IT-support profile**. If you've retargeted the bot, the profile-specific assertions are expected to fail until you rewrite them — see [CUSTOMIZATION.md §7](CUSTOMIZATION.md#7-updating-the-tests).

---

## Acceptance criteria

### Source and coverage

1. LinkedIn is the only job source.
2. All 8 paid keyword/country combinations are covered across two scheduled runs.
3. No more than 4 combinations are attempted per run.
4. Per-run and per-day dollar guards stop further paid searches **before** the ceiling is crossed.

### Role relevance

5. IT Support, Technical Support, Application Support, Service Desk/Help Desk and Customer Support/Customer Service titles are eligible when backed by normal technical or support evidence.
6. NOC Engineer and Cloud Support Engineer are **not** target roles.
7. "Help Desk" and "Helpdesk" score consistently (within 1 point).
8. Sales, business development, recruitment, marketing, real estate and insurance-sales false positives are suppressed.
9. A target role in the **title** scores higher than the same phrase appearing only in the description.
10. Technical support signals raise the score; negative commercial signals lower it.
11. An obvious sales title cannot alert merely because its description contains "customer support".
12. A related-but-not-identical title such as "L2 Application Support Engineer (Integration & Middleware)" is recognised as a match.

### Freshness and location

13. Postings with unknown or unparseable dates are rejected.
14. Postings older than `MAX_JOB_AGE_HOURS` are rejected.
15. Future-dated postings beyond a 5-minute tolerance are rejected.
16. Explicitly mismatched countries are rejected.
17. Unqualified Remote/Hybrid postings are rejected; a Remote posting that names the target country is accepted.

### Deduplication

18. The numeric LinkedIn job ID is preferred over scraper IDs.
19. Canonical URLs have tracking parameters removed, and existing records are matched by job key **or** URL.

### Delivery

20. Telegram retries 429 (using the server's `retry_after`), 5xx, and transient network errors.
21. Eligible jobs are ranked by relevance before delivery.
22. `MAX_ALERTS_PER_RUN` caps delivery; uncapped candidates stay eligible for a later run because they aren't marked as alerted.
23. Extracted experience/salary/shift/Arabic/visa signals are informational and never bypass the role, location or freshness gates.

### Schedule

24. Country-specific holidays skip only the affected country.
25. Runs outside the scheduled hour or minute window are blocked (systemd catch-up protection).
26. Non-working weekdays are blocked.

### Data

27. An existing `jobs.db` migrates in place; old rows survive and new columns appear.
28. Application status changes are recorded in `application_events`.
29. Result-volume anomalies are judged against each combination's own rolling median, not a fixed threshold.

### Security

30. CR/LF characters in untrusted LinkedIn text are collapsed before logging (log-injection prevention).
31. `_add_missing_columns()` rejects any table name outside its allowlist.
32. Allowed migration tables still migrate correctly after the allowlist was added.

---

## Core test matrix

| Input | Expected |
|---|---|
| `Technical Support Engineer` | HIGH score, alert eligible |
| `IT Support` (bare title) | alert eligible |
| `L2 Application Support Engineer (Integration & Middleware)` | alert eligible |
| `Help Desk Analyst` vs `Helpdesk Analyst` | scores within 1 point, both eligible |
| `Customer Service Representative` + technical description | eligible, Customer Support family |
| `Service Desk Analyst` + support signals | eligible |
| `NOC Engineer` | not eligible |
| `Cloud Support Engineer` | not eligible |
| `Software Engineer` + support in description | scores below a real support title |
| `Account Executive` + sales description | not eligible |
| `Business Development Executive` | not eligible |
| missing / invalid posting date | rejected |
| posted 40 hours ago | rejected |
| `Dubai, United Arab Emirates` under a Saudi search | rejected |
| `Remote` under a Saudi search | rejected |
| `Remote - Riyadh, Saudi Arabia` | accepted |
| same job with `trk` / `utm_*` parameters | one canonical job |
| Telegram 429 with `retry_after` | retried after the specified delay |
| Telegram 5xx | retried, retryable state preserved |
| 10:30 in the schedule timezone | blocked |
| 12:05 in the schedule timezone | allowed |
| non-working weekday at a valid hour | blocked |
| Saudi holiday date | blocks Saudi only, not Qatar |
| old-schema `jobs.db` | migrated; new columns added; old rows intact |
| title containing `\r\n` + a forged log line | newlines collapsed |
| table name `jobs; DROP TABLE jobs; --` | raises `ValueError` |
| result count far from rolling median | anomaly flagged, reason mentions the median |

---

## Cost QA

Paid retrieval stays at **4 broad search terms × 2 countries**. Expanding the local role vocabulary must never create new Apify search combinations — that's the whole point of the split between `SEARCH_KEYWORDS` (paid) and `ROLE_FAMILIES` (free, local).

The per-run result ceiling stays in place.

---

## Out of scope

No test should expect Bayt, GulfTalent, Naukrigulf, Indeed, Glassdoor or company career pages. Those sources are deliberately excluded.
