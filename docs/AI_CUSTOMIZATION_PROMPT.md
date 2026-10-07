# AI Customization Prompt

Use this prompt with ChatGPT, Claude, or another coding assistant to generate a FirstQueue profile for a different profession or country.

FirstQueue keeps the paid LinkedIn search layer small and does the detailed relevance filtering locally. The generated vocabulary should therefore be broad enough for search discovery and precise enough for local filtering.

```text
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

## After the AI generates the profile

1. Review the generated values before using them.
2. Paste the vocabulary into the matching sections of `config.py`.
3. Update `COUNTRIES` and `FOREIGN_LOCATION_TERMS`; the prompt does not generate those values.
4. Update the relevant tests in `tests.py` for the new role and countries.
5. Test both jobs you want accepted and adjacent jobs you want rejected.
6. Run the complete test suite before a real scheduled run.
7. Do a small manual run and tune false positives/false negatives from the alert reasons.

AI output is a starting point, not a guarantee of relevance. The project remains rule-based and auditable after customization.
