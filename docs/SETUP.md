# Setup

Complete setup from nothing. Assumes no prior server experience — every command is one you can copy and paste.

**Time needed:** about an hour, most of it waiting for Oracle to provision a server.

**Order matters.** Get the three credentials first (Apify, Telegram bot, Telegram chat ID), then the server, then the timer.

---

## Contents

1. [Apify account and API token](#1-apify-account-and-api-token)
2. [Telegram bot and chat ID](#2-telegram-bot-and-chat-id)
3. [A free server (Oracle Cloud)](#3-a-free-server-oracle-cloud)
4. [Install FirstQueue](#4-install-firstqueue)
5. [First test run](#5-first-test-run)
6. [Run it automatically (systemd)](#6-run-it-automatically-systemd)
7. [Cost control](#7-cost-control)
8. [Maintenance](#8-maintenance)

---

## 1. Apify account and API token

Apify runs the actor that retrieves LinkedIn job postings. This is the only part that costs money.

1. Sign up at **[apify.com](https://apify.com)** — free, no card required to start.
2. New accounts get **$5 of free platform credit per month**.
3. Go to **Settings → API & Integrations**.
4. Copy your **Personal API token**. It starts with `apify_api_`.
5. Keep it somewhere safe for the moment — it goes into `.env` later.

### About the actor

`config.py` ships with `APIFY_ACTOR_ID = "2rJKkhh7vjpX7pvjg"` — the LinkedIn jobs actor this project was built and tested against. You can view it at:

```
https://console.apify.com/actors/2rJKkhh7vjpX7pvjg
```

**Check its current pricing before you rely on the cost estimates in this repo.** Actor pricing changes, and `APIFY_COST_PER_1000_RESULTS = 0.70` in `config.py` is what it cost when this was written. If the actor you use charges differently, update that number so the spending guards stay accurate.

If you'd rather use a different LinkedIn jobs actor from the [Apify Store](https://apify.com/store), you can — but check the input field names it expects against `fetch_jobs()` in `main.py`, because every actor names its inputs differently:

```python
run_input = {
    "keywords": [keyword], "location": country,
    "maxItems": config.MAX_RESULTS_PER_COMBO, "maxResults": config.MAX_RESULTS_PER_COMBO,
    "datePosted": "past24Hours", "publishedAt": "r86400",
}
```

> **A note on terms of service:** automated collection of LinkedIn data may conflict with LinkedIn's Terms of Service, even through a third party. You're responsible for your own use. This is built for one person monitoring their own job search at low volume.

---

## 2. Telegram bot and chat ID

You need two values: the bot's token, and your own numeric chat ID.

### Create the bot

1. Open Telegram and message **[@BotFather](https://t.me/botfather)**.
2. Send `/newbot`.
3. Give it a display name (anything — "My Job Alerts").
4. Give it a username ending in `bot` (for example, `<YOUR_BOT_USERNAME>`). It must be unique.
5. BotFather replies with your bot token. Treat it as a password and keep it private.

**That token is a password.** Anyone holding it controls your bot. Never commit it or paste it into a screenshot.

### Get your chat ID

The bot can only message you after you've messaged it first.

1. Find your new bot in Telegram search and press **Start**, or just send it `hello`.
2. Open this URL in a browser, with your real token substituted in:

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

3. You'll get JSON back. Find the chat ID:

```json
{"result":[{"message":{"chat":{"id":<YOUR_CHAT_ID>,"type":"private"}}}]}
```

Here the chat ID is `123456789`. It's a number, not your `@username`.

**Empty `{"ok":true,"result":[]}`?** You haven't messaged the bot yet, or Telegram already cleared the update. Send it another message and reload.

---

## 3. A free server (Oracle Cloud)

You need a machine that's always on. Oracle Cloud's **Always Free** tier covers this permanently — not a trial that expires.

Any always-on Linux box works equally well: a Raspberry Pi at home, an old laptop, a $4/month VPS elsewhere. If you already have one, skip to [step 4](#4-install-firstqueue).

### What the Always Free tier includes

As of writing, Oracle's Always Free tier includes ARM (Ampere A1) compute plus two small AMD VMs. **Verify the current terms at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)** — Oracle changes this periodically, and this document may be out of date.

FirstQueue is light. It runs for a minute or two, four times a day, and sleeps otherwise. The smallest free instance is plenty, unless you enable the optional embedding model (that wants ~1GB RAM free).

### Create the instance

1. Sign up at **[oracle.com/cloud/free](https://www.oracle.com/cloud/free/)**. A card is required for identity verification, but Always Free resources aren't charged. **Set your account to stay on the free tier** rather than upgrading to pay-as-you-go if you want a hard guarantee against charges.
2. In the console: **Compute → Instances → Create instance**.
3. **Image:** Ubuntu 22.04 or 24.04. (Both ship Python 3.10+, which this project needs. Oracle Linux works too but the commands below are Ubuntu's.)
4. **Shape:** any Always Free eligible shape — it'll be labelled.
5. **SSH keys:** choose **Generate a key pair for me** and **download the private key**. You cannot download it again later, and without it you cannot log in.
6. Click **Create** and wait for the state to become **Running**. Note the **public IP address**.

> **"Out of host capacity"** on ARM shapes is common and not your mistake — free ARM capacity in popular regions runs out. Either pick an AMD micro shape instead, or retry later. Picking a less busy region when you create your account helps.

### Connect

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@YOUR_SERVER_IP
```

The username is `ubuntu` for Ubuntu images (`opc` for Oracle Linux).

On Windows, use the same command in PowerShell, or [PuTTY](https://www.putty.org/) with the key converted via PuTTYgen.

### Prepare the server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
python3 --version    # must be 3.10 or higher
```

No inbound ports need opening. FirstQueue only makes outbound requests.

---

## 4. Install FirstQueue

On the server:

```bash
cd ~
git clone https://github.com/ashifmomin/firstqueue.git
cd firstqueue

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Create your credentials file:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill in the three values — no quotes, no spaces around `=`. Use your real values only in `.env`; never commit this file:

```
APIFY_API_TOKEN=<YOUR_APIFY_API_TOKEN>
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
TELEGRAM_CHAT_ID=<YOUR_TELEGRAM_CHAT_ID>
```

Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

`chmod 600` matters — it means only your user can read the file. `.env` is gitignored, so it will never be committed.

### Confirm the code is healthy

```bash
python3 -m unittest tests.py
```

Expect `Ran 34 tests ... OK`. If tests fail here, something's wrong with the install — don't continue.

---

## 5. First test run

This makes **real Apify and Telegram calls** and spends real Apify credit (a few cents).

```bash
cd ~/firstqueue
source venv/bin/activate
set -a && source .env && set +a
IGNORE_SCHEDULE_GUARDS=1 python3 main.py
```

`IGNORE_SCHEDULE_GUARDS=1` bypasses the weekday/hour/holiday checks so you can test at any time.

**What you should see:** log lines for each search, then either `ALERT SENT` lines and Telegram messages, or a summary showing everything was filtered out.

**Zero alerts is a normal first result.** The bot only accepts jobs posted in the last 24 hours, in your target countries, matching your role vocabulary. On a quiet day there genuinely may be none. Check the summary line to see where postings were dropped:

```
fetched=287 matched=3 alerted=3 stale=201 unknown_date=12 wrong_location=48 duplicate=0 low_relevance=23
```

That tells you the pipeline is working. If `fetched=0`, the Apify call is the problem — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 6. Run it automatically (systemd)

systemd will run the bot on a schedule and restart cleanly after a reboot.

### Install the unit files

The repo ships example unit files. They contain placeholders rather than a specific Linux username or home path. Copy them and replace the placeholders before installing:

```bash
cp deploy/firstqueue.service.example deploy/firstqueue.service
cp deploy/firstqueue.timer.example deploy/firstqueue.timer
nano deploy/firstqueue.service
```

```ini
[Unit]
Description=FirstQueue job alert bot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=YOUR_LINUX_USERNAME
WorkingDirectory=/home/YOUR_LINUX_USERNAME/firstqueue
EnvironmentFile=/home/YOUR_LINUX_USERNAME/firstqueue/.env
ExecStart=/home/YOUR_LINUX_USERNAME/firstqueue/venv/bin/python3 /home/YOUR_LINUX_USERNAME/firstqueue/main.py
```

Then install and enable:

```bash
sudo cp deploy/firstqueue.service /etc/systemd/system/firstqueue.service
sudo cp deploy/firstqueue.timer   /etc/systemd/system/firstqueue.timer
sudo systemctl daemon-reload
sudo systemctl enable --now firstqueue.timer
```

### Check it

```bash
systemctl list-timers firstqueue.timer   # when it fires next
systemctl status firstqueue.timer
sudo journalctl -u firstqueue.service -n 50 --no-pager
```

### Getting the times right

**The timer is in UTC. `config.py` is in your local timezone. They have to agree.**

The shipped timer:

```ini
OnCalendar=Sun,Mon,Tue,Wed,Thu 06,09,12,15:00:00 UTC
```

06:00 / 09:00 / 12:00 / 15:00 UTC = **09:00 / 12:00 / 15:00 / 18:00 Gulf time (UTC+3)**, matching `SCHEDULE_HOURS` in `config.py`.

If you change your schedule, convert correctly — subtract your UTC offset from each local hour:

| Your timezone | Local target | UTC in the timer |
|---|---|---|
| UTC+3 (Gulf) | 09:00 | 06:00 |
| UTC+5:30 (India) | 09:00 | 03:30 |
| UTC+1 (Central Europe) | 09:00 | 08:00 |
| UTC−5 (US Eastern) | 09:00 | 14:00 |

**Both guards must agree or nothing will ever run.** The bot independently refuses to run outside `SCHEDULE_HOURS` (plus `SCHEDULE_HOUR_GRACE_MINUTES`), so a timer that fires at a time `config.py` doesn't allow produces a run that immediately exits with `skipped: outside scheduled Gulf hour`. If you see that in the logs, your two schedules disagree.

`Persistent=true` is deliberately left on so a missed run is attempted after a reboot — the bot's own minute-window guard is what stops that attempt from firing at a nonsense hour.

---

## 7. Cost control

Apify charges **per result returned**, not per search. The guards in `config.py` are hard ceilings — the bot stops before crossing them.

### What it actually costs

At $0.70 per 1,000 results:

| Configuration | Results/run | Cost/run | Runs/day | **Per day** | **Per 30 days** |
|---|---|---|---|---|---|
| Default (4 searches × 150) | up to 600 | up to $0.42 | 4 | up to $1.68 | up to ~$50 |
| Default, realistic yield | ~300 | ~$0.21 | 4 | ~$0.84 | ~$25 |
| **2 runs/day, 100 max** | ~200 | ~$0.14 | 2 | ~$0.28 | **~$8** |
| **1 run/day, 100 max** | ~200 | ~$0.14 | 1 | ~$0.14 | **~$4 — inside free credit** |

"Realistic yield" matters: a 24-hour-filtered search usually returns far fewer than the 150 ceiling, so you're generally charged well under the worst case.

**To stay inside the $5/month free credit**, use one or two runs a day:

```python
# config.py
SCHEDULE_HOURS = {9: "09:00", 15: "15:00"}   # two slots instead of four
MAX_RESULTS_PER_COMBO = 100                   # instead of 150
MAX_APIFY_COST_PER_DAY = 0.20                 # a tighter hard ceiling
```

Then update the timer to match (`06,12:00:00 UTC` for 09:00/15:00 Gulf).

### Watch your spend

```bash
sqlite3 jobs.db "SELECT date(timestamp) AS day, ROUND(SUM(apify_cost_estimate),4) AS usd
                 FROM run_history WHERE keyword!='__RUN_TOTAL__'
                 GROUP BY day ORDER BY day DESC LIMIT 14;"
```

These are the bot's own estimates. **Check them against the real figure in the Apify console** — if the actor's pricing changed, your estimates are wrong and so are your guards.

---

## 8. Maintenance

**Update public holidays each year.** `PUBLIC_HOLIDAYS` in `config.py` has fixed 2026 dates. Religious holidays move. An out-of-date list means the bot runs on holidays — harmless, just wasted credit.

**Check in monthly.** The anomaly detector warns you via Telegram when result volumes swing, which usually means the actor or LinkedIn changed something. Don't ignore those messages.

**Keep dependencies patched.**

```bash
cd ~/firstqueue && source venv/bin/activate
pip list --outdated
```

**Back up the database** if your application history matters to you:

```bash
sqlite3 jobs.db ".backup '$HOME/jobs-backup-$(date +%F).db'"
```

**Watch the log size.** `bot.log` rotates automatically at 2MB with 5 backups, so it's capped at roughly 12MB.

---

## Next

- Retarget it to your own role and country → [CUSTOMIZATION.md](CUSTOMIZATION.md)
- Something isn't working → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Understand the internals → [ARCHITECTURE.md](ARCHITECTURE.md)
