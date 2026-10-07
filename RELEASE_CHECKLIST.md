# FirstQueue v0.1.0 Release Checklist

## Source and security

- [x] No real credentials in the source tree
- [x] `.env` is gitignored; `.env.example` contains placeholders only
- [x] Log-injection hardening is present
- [x] Database migration table names are allowlisted
- [x] `requests` is pinned to 2.33.0
- [x] Fatal notification failure is logged explicitly
- [x] Security documentation is included
- [ ] Final local secret scan passes with no real credentials

## Tests

- [ ] `python3 -m py_compile main.py config.py relevance.py tests.py`
- [ ] `python3 -m unittest -v tests.py` — 34 tests pass
- [ ] `git diff --check` passes
- [ ] GitHub Actions workflow is present and uses supported Python versions

## Documentation

- [x] README explains scope and limitations
- [x] Setup guide is end-to-end
- [x] Customization guide explains role/country changes
- [x] AI customization prompt is included
- [x] Architecture and QA docs are included
- [x] Troubleshooting guide uses the current systemd unit names
- [x] GitHub publishing guide is included
- [x] Systemd files are generic `.example` templates
- [ ] Replace any repository URL placeholders if publishing under a different account

## Repository hygiene

- [ ] Remove local `.git` history if this ZIP is being used as a fresh source export
- [ ] Initialize Git and create the `v0.1.0` commit
- [ ] Push to the intended GitHub repository
- [ ] Create GitHub release `v0.1.0`

## Before real deployment

- [ ] Use Python 3.10+
- [ ] Create a private `.env` with real credentials
- [ ] `chmod 600 .env`
- [ ] Review current Apify actor pricing
- [ ] Review current LinkedIn and provider terms
- [ ] Configure `config.py` for the user's target role/countries
- [ ] Verify the systemd timer matches `SCHEDULE_HOURS` and `SCHEDULE_TZ`
- [ ] Run one controlled manual test before enabling the timer
