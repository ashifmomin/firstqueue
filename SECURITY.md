# Security

## Reporting a vulnerability

Open a [GitHub issue](../../issues) for anything non-sensitive.

For something exploitable, please use GitHub's **private vulnerability reporting** (Security tab → Report a vulnerability) rather than a public issue, so it can be fixed before it's widely known.

This is a personal project maintained in spare time. Expect a response within a week or so, not within hours.

---

## What this project holds

Running FirstQueue means three secrets live on your server:

| Secret | Risk if leaked |
|---|---|
| `APIFY_API_TOKEN` | full access to your Apify account — someone can spend your credit |
| `TELEGRAM_BOT_TOKEN` | full control of your bot — read its messages, send as it |
| `TELEGRAM_CHAT_ID` | not a credential, but it identifies you |

Plus two files containing personal data:

- **`jobs.db`** — every job you've been alerted to, and your application history
- **`bot.log`** — job titles, company names and URLs

All five are in `.gitignore`. **Never commit them.**

---

## How credentials are handled

- Read from environment variables only — see `config.py` lines 20–24.
- In production they come from `.env`, loaded by systemd's `EnvironmentFile=`.
- `.env` is gitignored, and `.env.example` holds only empty placeholders.
- No credential is ever logged. Telegram's token appears only inside the request URL, which is never logged.
- `main.py` aborts with a clear message if any of the three is missing, rather than failing obscurely mid-run.

### Protect your `.env`

```bash
chmod 600 .env        # only your user can read it
ls -l .env            # expect -rw-------
```

---

## If you leak a token

Revoke first, investigate after. Both are instant and free to replace.

**Apify:** Console → Settings → API & Integrations → delete the token and create a new one. Then check your usage and billing for runs you didn't start.

**Telegram:** message [@BotFather](https://t.me/botfather) → `/revoke`, then `/token` for a new one.

Then update `.env` and `sudo systemctl restart firstqueue.timer`.

**If you committed a secret to git, revoking is the only real fix.** Rewriting history doesn't help — the value may already have been cloned, cached or scraped. Treat anything that ever reached a public repository as compromised.

---

## Known hardening already applied

The project has been security-tested against itself. Fixed issues:

**Log injection (CWE-117).** Job titles, company names and URLs come from LinkedIn and are untrusted. A crafted title containing `\r\n` plus a fake timestamp could forge log entries. `_sanitize_log()` collapses line-breaking characters before any untrusted value is logged, with regression test coverage.

**SQL identifier injection in migrations.** Table names can't be parameterised in SQL, so `_add_missing_columns()` interpolates them — and validates against an allowlist (`{"jobs", "run_history"}`) first. A test asserts `"jobs; DROP TABLE jobs; --"` raises `ValueError`.

**Dependency vulnerability.** `requests` pinned forward to 2.33.0 for CVE-2026-25645. **Don't pin it back** to stay on an older Python — upgrade Python instead.

**Silent failure in the crash handler.** A bare exception handler in the fatal-notification path was replaced with an explicit handler plus a diagnostic log line, so a failed crash notification is recorded rather than swallowed.

**HTML injection into Telegram.** Every value interpolated into an alert passes through `escape_html()`, so a job title containing `<` can't break the message parse or inject markup.

---

## Keeping a deployment safe

```bash
# patch the OS
sudo apt update && sudo apt upgrade -y

# check dependencies
cd ~/firstqueue && source venv/bin/activate && pip list --outdated
```

- No inbound ports are needed. Don't open any.
- Use SSH keys, not passwords.
- `.env` at `chmod 600`.
- Back up `jobs.db` somewhere private, not to a public repository.

---

## Scope

**In scope:** credential handling, injection into logs/SQL/Telegram, dependency vulnerabilities, anything letting a crafted job posting affect the host.

**Out of scope:** Apify's platform and actors, Telegram's API, your VPS provider, and the question of whether automated LinkedIn data collection complies with LinkedIn's Terms of Service — that last one is a legal matter for each user, not a vulnerability. See the note at the end of the README.
