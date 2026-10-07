# Publishing FirstQueue to GitHub

This guide is for the public open-source repository. It assumes you have already created an empty GitHub repository named `firstqueue` under your account.

## 1. Review the working tree

From the project root:

```bash
git status
git diff --check
```

Make sure no `.env`, database, log, virtual environment, cache, IDE files, or personal documents are present.

## 2. Run the local checks

```bash
python3 -m py_compile main.py config.py relevance.py tests.py
python3 -m unittest -v tests.py
```

The current release should report **34 passing tests**.

## 3. Check for secrets and personal paths

Search the repository before committing:

```bash
grep -RInE 'APIFY_API_TOKEN=|TELEGRAM_BOT_TOKEN=|TELEGRAM_CHAT_ID=|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|/home/[A-Za-z0-9_.-]+/|C:\\Users\\' . \
  --exclude-dir=.git --exclude='*.pyc'
```

Expected matches should be documentation placeholders/templates only. Never publish a real token, private key, `.env`, database, or log.

## 4. Create the first commit

```bash
git add .
git diff --cached --check
git commit -m "Release FirstQueue v0.1.0"
```

## 5. Connect the GitHub repository

Replace the URL with your own repository if it differs:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/firstqueue.git
git push -u origin main
```

## 6. Create the release

Tag the release after the push:

```bash
git tag -a v0.1.0 -m "FirstQueue v0.1.0"
git push origin v0.1.0
```

Create the GitHub release from tag `v0.1.0`. Use the release notes in `CHANGELOG.md` as the source for the release summary.

## Important scope note

FirstQueue is LinkedIn-only and does not automate applications. Review LinkedIn's current terms and the terms of any third-party data provider before deploying it. Users are responsible for how they operate their own instance.
