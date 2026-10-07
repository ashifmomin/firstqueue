# Customization

The defaults look for **IT support roles in Qatar and Saudi Arabia**, on a Gulf working week. This guide retargets it to your role, your countries and your schedule.

Everything you need is in **Part 1 of `config.py`**, except the role vocabulary, which is Part 2.

**Always re-run the tests after editing:**

```bash
python3 -m unittest tests.py
```

Some tests assert the *default* IT-support behaviour (that "NOC Engineer" is rejected, that there are exactly 8 search combinations, that specific Gulf holidays apply). **If you change the profile, those tests are supposed to fail** — they're testing the old profile. Rewrite them to assert your profile instead; [the test section below](#7-updating-the-tests) shows how.

---

## Contents

1. [Change the country](#1-change-the-country)
2. [Change the role](#2-change-the-role) ← the big one
3. [Change the schedule](#3-change-the-schedule)
4. [Change how strict it is](#4-change-how-strict-it-is)
5. [Change the spending limits](#5-change-the-spending-limits)
6. [Change what's in the alert](#6-change-whats-in-the-alert)
7. [Updating the tests](#7-updating-the-tests)
8. [The AI prompt](#8-the-ai-prompt) ← generates your vocabulary for you

---

## 1. Change the country

Three settings, and they must agree with each other.

```python
# config.py — Part 1a

# What gets searched. Keys are labels used in alerts; values go to the Apify actor.
COUNTRIES = {"United Arab Emirates": "United Arab Emirates", "Oman": "Oman"}

# Words that PROVE a posting is really in each country.
# Without these, every posting gets rejected.
COUNTRY_LOCATION_TERMS = {
    "United Arab Emirates": [
        "united arab emirates", "uae", "dubai", "abu dhabi", "sharjah",
        "ajman", "ras al khaimah", "fujairah", "al ain",
    ],
    "Oman": ["oman", "muscat", "salalah", "sohar", "nizwa"],
}

# Words that mean "somewhere else". Remove your target countries from this list.
FOREIGN_LOCATION_TERMS = [
    "qatar", "doha", "saudi arabia", "riyadh", "jeddah", "kuwait", "bahrain",
    "united kingdom", "united states", "india",
]
```

**Why `COUNTRY_LOCATION_TERMS` matters.** The location gate rejects any posting whose location text doesn't name your target country or one of its cities. This is deliberate: a posting that just says "Remote" doesn't prove which country it's hiring in. So include the country name, every major city, and common spellings.

The bot refuses to start if a country in `COUNTRIES` has no location terms, rather than silently rejecting everything.

**Include spelling variants.** `"al khobar"` and `"khobar"`; `"makkah"` and `"mecca"`. Lowercase only — matching is case-insensitive via lowercasing.

**Searching one country?** Fine — just one entry in both dicts. That halves your search combinations and your cost.

---

## 2. Change the role

This is the real work. Four things to replace:

### 2a. The paid searches

```python
# config.py — Part 1b
SEARCH_KEYWORDS = [
    "Registered Nurse",
    "Staff Nurse",
    "ICU Nurse",
]
```

**Keep this list short and broad.** Every keyword multiplies your Apify bill: `keywords × countries = paid searches`. 3 keywords × 2 countries = 6 combinations.

Broad here, narrow in `ROLE_FAMILIES` — that filtering is local and free. Search "Registered Nurse", don't search 15 nursing specialities.

### 2b. Role families

The strongest signal in the whole engine: a match here against the job **title**.

```python
# config.py — Part 2
ROLE_FAMILIES = {
    "Critical Care": [
        "icu nurse", "intensive care nurse", "critical care nurse",
        "ccu nurse", "coronary care nurse",
    ],
    "General Nursing": [
        "registered nurse", "staff nurse", "ward nurse",
        "general nurse", "rn", "charge nurse",
    ],
    "Emergency": [
        "emergency nurse", "er nurse", "a&e nurse",
        "emergency department nurse", "triage nurse",
    ],
}
```

Group by family so alerts can tell you *which kind* of role matched. Write every realistic title variant, lowercase. Include abbreviations people actually use in postings.

### 2c. Confirming signals

Evidence that a posting is genuinely in your field. These add points.

```python
TECHNICAL_SIGNALS = [
    "patient care", "clinical", "ventilator", "iv", "cannulation",
    "medication administration", "bls", "acls", "patient assessment",
    "electronic medical record", "emr", "triage", "wound care",
]

SUPPORT_SIGNALS = [
    "shift", "rotational", "ward", "bedside", "handover",
    "care plan", "multidisciplinary", "patient safety",
]
```

Both lists work identically — two lists with separate point caps (max 17 and 12 points). Put your strongest domain terms in `TECHNICAL_SIGNALS` since it carries the bigger cap.

### 2d. Negative signals

Titles that mean "not this job", however the description reads. A title hit here is a heavy penalty (42 points each).

```python
NEGATIVE_TITLE_TERMS = [
    "medical sales", "pharmaceutical sales", "medical representative",
    "recruiter", "recruitment consultant", "insurance",
    "nursing home sales", "medical equipment sales",
]

NEGATIVE_DESCRIPTION_TERMS = [
    "commission based", "sales target", "sales quota", "lead generation",
]
```

**This is what keeps your alerts clean.** Work out what junk your search returns, then add those titles here. For IT support it was sales and recruitment roles stuffing "customer support" into their descriptions. For nursing it's medical device sales. Every field has its own version.

### 2e. The description-only list

Terms that count for less when they appear only in the description, not the title:

```python
DESCRIPTION_ROLE_PATTERNS = [
    "patient care", "nursing care", "clinical duties",
    "ward management", "bedside nursing",
]
```

### 2f. The semantic query (optional)

Only used if you enable the embedding model:

```python
RELEVANCE_QUERY = "Registered Nurse ICU Critical Care Emergency Nursing United Arab Emirates Oman"
```

---

## 3. Change the schedule

```python
# config.py — Part 1c

# Your timezone
SCHEDULE_TZ = timezone(timedelta(hours=5, minutes=30))   # IST
# SCHEDULE_TZ = timezone(timedelta(hours=4))             # Gulf (UAE/Oman)
# SCHEDULE_TZ = timezone(timedelta(hours=0))             # UTC

# Days OFF. Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
NON_WORKING_WEEKDAYS = {5, 6}    # Sat/Sun weekend
# NON_WORKING_WEEKDAYS = {4, 5}  # Fri/Sat — Gulf working week
# NON_WORKING_WEEKDAYS = set()   # run every day

# Hours (in SCHEDULE_TZ) when a run is allowed
SCHEDULE_HOURS = {9: "09:00", 18: "18:00"}

# Your holidays
PUBLIC_HOLIDAYS = {
    "United Arab Emirates": {"2026-12-02", "2026-12-03"},
    "Oman": {"2026-11-18"},
}
```

**You must also update the systemd timer, in UTC.** The bot independently refuses to run outside `SCHEDULE_HOURS`, so if the two disagree, every run exits immediately with `skipped: outside scheduled Gulf hour`.

For `SCHEDULE_HOURS = {9, 18}` in IST (UTC+5:30), subtract 5:30 → 03:30 and 12:30 UTC:

```ini
# deploy/firstqueue.timer
OnCalendar=Mon,Tue,Wed,Thu,Fri 03:30:00 UTC
OnCalendar=Mon,Tue,Wed,Thu,Fri 12:30:00 UTC
```

Then:

```bash
cp deploy/firstqueue.timer.example deploy/firstqueue.timer
# Edit deploy/firstqueue.timer to match your schedule, then:
sudo cp deploy/firstqueue.timer /etc/systemd/system/firstqueue.timer
sudo systemctl daemon-reload
sudo systemctl restart firstqueue.timer
systemctl list-timers firstqueue.timer
```

### Fresher than 24 hours?

```python
MAX_JOB_AGE_HOURS = 12   # only postings from the last 12 hours
```

Only worth it if you run often enough to catch them — with one run a day, a 12-hour window means you miss half the postings.

---

## 4. Change how strict it is

```python
# config.py — Part 1f
RELEVANCE_ALERT_THRESHOLD = 55.0              # below this: no alert
RELEVANCE_HIGH_THRESHOLD = 78.0               # at/above: labelled HIGH
RELEVANCE_OVERRIDE_NEGATIVE_THRESHOLD = 82.0  # needed to survive a negative hit
```

| Symptom | Change |
|---|---|
| Too many irrelevant alerts | Raise `ALERT_THRESHOLD` to 65–70 |
| Missing jobs you'd have wanted | Lower `ALERT_THRESHOLD` to 45–50 |
| Good jobs blocked by one bad word | Lower `OVERRIDE_NEGATIVE_THRESHOLD` to ~75 |
| Junk sneaking through with high scores | Add its title to `NEGATIVE_TITLE_TERMS` — better than raising the threshold |

**Tune the vocabulary before the thresholds.** A wrong alert usually means a missing negative term, not a threshold that's too low. Raising the threshold loses good matches too.

### See how a title scores

```bash
source venv/bin/activate
python3 -c "
import relevance, json
r = relevance.score_job('Senior ICU Nurse', 'Ventilator management, patient assessment, BLS certified.')
print(json.dumps(r, indent=2))
"
```

That prints the score, band, matched families and the reasons — the fastest way to work out why something did or didn't alert.

### The optional embedding model

```bash
pip install -r requirements-semantic.txt
# then in .env:
ENABLE_EMBEDDING_MODEL=1
```

Adds semantic similarity as 20% of the final score, so "Patient Care Technician" can register as related to nursing without being in your vocabulary. Costs ~90MB of download and noticeably more RAM. On a 1GB free VM, check it fits. **It's off by default and the bot is fully functional without it.**

---

## 5. Change the spending limits

```python
# config.py — Part 1d
MAX_RESULTS_PER_COMBO = 100       # fewer results per search = cheaper
MAX_COMBOS_PER_RUN = 2            # fewer paid searches per run
SAFETY_MAX_RESULTS_PER_RUN = 200  # keep = MAX_RESULTS_PER_COMBO × MAX_COMBOS_PER_RUN
MAX_APIFY_COST_PER_RUN = 0.20
MAX_APIFY_COST_PER_DAY = 0.50
```

`MAX_COMBOS_PER_RUN` controls rotation: with 6 combinations and 2 per run, full coverage takes 3 runs. The rotation cursor persists in the database, so coverage continues across restarts.

See the [cost table in SETUP.md](SETUP.md#7-cost-control) for what each configuration costs.

---

## 6. Change what's in the alert

Edit `build_alert()` in `main.py`. It builds a Telegram HTML message — only `<b>`, `<i>`, `<code>`, `<a>` are supported.

The extracted facts (experience, salary, shift, Arabic, visa) come from `extract_job_signals()`, which is regex over the description. To extract something else — a licence requirement, say:

```python
# in extract_job_signals(), add to the returned dict:
"license_required": bool(re.search(r"dha|haad|moh|dataflow|prometric", low)),
```

Then add a line to `build_alert()`. Keep these informational — they shouldn't bypass the role, location or freshness gates.

---

## 7. Updating the tests

`tests.py` asserts the default IT-support profile. After retargeting, some tests *should* fail. Rewrite them to assert yours:

```python
# tests.py
class RelevanceTests(unittest.TestCase):
    def test_exact_title_scores_high(self):
        r = relevance.score_job("ICU Nurse", "Ventilator management, patient assessment, BLS.")
        self.assertGreaterEqual(r["score"], config.RELEVANCE_HIGH_THRESHOLD)
        self.assertTrue(relevance.should_alert(r))

    def test_medical_sales_is_suppressed(self):
        r = relevance.score_job("Medical Sales Representative",
                                "Sell devices to hospitals, meet sales quota.")
        self.assertFalse(relevance.should_alert(r))
```

Also update:

- `test_all_eight_combos_exist` — change `8` to `len(SEARCH_KEYWORDS) × len(COUNTRIES)`
- `test_saudi_location` / `test_qatar_location` / `test_mismatched_location` — use your countries
- `test_country_holiday_is_country_specific` — use a date from your `PUBLIC_HOLIDAYS`
- `ScheduleTests` — use hours from your `SCHEDULE_HOURS` and days matching `NON_WORKING_WEEKDAYS`

**Don't delete tests to make them pass.** They're what tells you the filtering still works after a change.

---

## 8. The AI prompt

Writing the vocabulary by hand is tedious. Paste this into Claude, ChatGPT or any assistant, fill in the three blanks, and it'll generate the lot.

```
I'm configuring an open-source job alert bot called FirstQueue. It filters job
postings using Python lists of keywords. I need you to generate the vocabulary
for my profession.

MY DETAILS
- Role(s) I want: ____________________
  (e.g. "Registered Nurse, ICU and emergency specifically")
- Countries I'm searching: ____________________
  (e.g. "UAE and Oman")
- Junk I want excluded: ____________________
  (e.g. "medical device sales, recruiters, anything commission-based")

GENERATE THESE SEVEN PYTHON VALUES

1. SEARCH_KEYWORDS — a list of 3-4 BROAD search terms. These are PAID searches
   charged per result, so keep it minimal and broad. Narrowing happens locally
   and free in the next list.

2. ROLE_FAMILIES — a dict grouping specific job titles into 3-6 named families.
   A match here against a job TITLE is the strongest signal in the engine.
   Include every realistic title variant and the abbreviations that actually
   appear in postings. All values lowercase.

3. TECHNICAL_SIGNALS — a list of 20-30 tools, certifications, systems and
   practices that confirm a posting is genuinely in this field. Lowercase.

4. SUPPORT_SIGNALS — a list of 10-20 secondary terms about working conditions
   and responsibilities typical of this field. Lowercase.

5. NEGATIVE_TITLE_TERMS — a list of 10-20 job titles that look superficially
   similar or come up in the same searches but are NOT this job. This is the
   most important list for alert quality. Think about which adjacent roles
   contaminate searches for this profession — especially sales and recruitment
   roles that reuse the field's vocabulary.

6. NEGATIVE_DESCRIPTION_TERMS — a list of 5-10 phrases in a job DESCRIPTION
   that signal the wrong kind of role. Lowercase.

7. COUNTRY_LOCATION_TERMS — a dict mapping each country I named to a list of
   that country's name, common abbreviations and all its major cities,
   including alternative spellings (e.g. both "mecca" and "makkah").
   Lowercase. This is what proves a posting is really in that country, so be
   thorough — a city you miss is a job you never see.

RULES
- Output valid Python I can paste straight into config.py, with the exact
  variable names above.
- Lowercase every string except ROLE_FAMILIES dict keys and
  COUNTRY_LOCATION_TERMS dict keys.
- No placeholders or "..." — give me the complete lists.
- Add a brief comment above each list explaining what it does.
```

### After pasting the result in

1. Paste each value over the matching one in `config.py`.
2. Also update `COUNTRIES` (Part 1a) and `FOREIGN_LOCATION_TERMS` (remove your targets from it) — the prompt doesn't cover those.
3. Test a handful of real titles with the `score_job` snippet in [section 4](#see-how-a-title-scores) — including ones you want *rejected*.
4. Update `tests.py` as per [section 7](#7-updating-the-tests).
5. Do a manual run: `IGNORE_SCHEDULE_GUARDS=1 python3 main.py`.
6. Read the first day of alerts critically. Anything wrong that got through goes into `NEGATIVE_TITLE_TERMS`.

Expect to tune for a few days. The first vocabulary is never quite right, and the `low_relevance` counter in the run summary tells you whether you're filtering too hard.

---

## Contributing your profile back

If you build a working vocabulary for another profession, a pull request adding it as an example would help the next person. See [CONTRIBUTING.md](../CONTRIBUTING.md).
