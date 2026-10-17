# Internship Job Alert 2027

A no-dependency Python MVP that checks public job APIs daily, scores internship listings, avoids duplicate notifications, and optionally sends email. Built for a third-year computer-science engineering student seeking a ~3-month internship from June 2027.

## Start locally (Ubuntu)

```bash
python3 job_alert.py
```

The first run prints matching listings and creates `seen_jobs.sqlite3`. Later runs print only newly seen listings. Delete the database to reset history.

## Email notifications (Gmail example)

1. Enable two-step verification on your Google account and create an **app password** if your account supports it. Do not use your normal Google password.
2. Set these environment variables locally, or configure them as GitHub Actions repository secrets:
   - `SMTP_HOST`: `smtp.gmail.com`
   - `SMTP_PORT`: `465`
   - `SMTP_USER`: your Gmail address
   - `SMTP_PASSWORD`: your Google app password
   - `ALERT_TO`: destination email address
3. For local testing:

```bash
export SMTP_HOST=smtp.gmail.com SMTP_PORT=465
export SMTP_USER='you@gmail.com' ALERT_TO='you@gmail.com'
read -rs SMTP_PASSWORD; export SMTP_PASSWORD; echo
python3 job_alert.py
```

Never commit credentials to GitHub.

## Run automatically on GitHub

1. Create a **private** GitHub repository and upload all project files, including `.github/workflows/job-alert.yml`.
2. In repository **Settings → Secrets and variables → Actions**, create the five secrets listed above.
3. Open **Actions → Internship Job Alert → Run workflow** to test.
4. GitHub Actions checks every day at 07:20 UTC (execution time is not guaranteed). The workflow commits the SQLite deduplication database so subsequent runs don't repeat the same listings. Ensure Actions have **Read and write permissions** in repository Settings → Actions → General → Workflow permissions.

GitHub Actions scheduling can be delayed, disabled for inactive public repositories, or subject to usage quotas. Private repositories may have billing limits. This is not an always-on monitoring service.

## Configure

Edit `config.json`: watchlist, skills, locations, minimum score. Set `only_watchlisted_companies` to `true` to see only matching employers (but many jobs will disappear). To add **official ATS boards**, populate `greenhouse_boards` or `lever_sites` with verified board slugs, not company names guessed from the watchlist. Example: a Greenhouse URL shaped like `boards.greenhouse.io/SLUG` implies board slug `SLUG` (verify that its public API responds). These boards are not populated by default.

## Important limitations

- **Coverage is partial**: Arbeitnow and Remotive are broad public feeds, not direct Airbus/Safran/Thales/Capgemini feeds. This MVP does not yet systematically track the named employers. Official ATS connectors require verified board IDs or permitted APIs.
- **No guarantee of 2027 start**: date/duration often aren't structured in public feeds. The system ranks mentions of June 2027 and three months but does not assert a match.
- **Eligibility requires manual verification**: language, visa, nationality, work authorization, academic level and dates must be checked on the official posting.
- **Location is a ranking factor, not a hard filter**: remote or unspecified locations can appear. This avoids dropping opportunities without a structured location.
- **False positives are possible**: keyword filtering is deliberately simple; job-board results are not an endorsement or application.
- **API availability may change**: sources can rate-limit or change schema. Failed sources are logged and do not stop successful ones.
- **Job alerts are sent only if SMTP is configured**; otherwise results appear in console logs.

## Future extensions

Add company-specific approved APIs, better French internship eligibility parsing, a small dashboard, and a weekly digest. Avoid scraping websites that prohibit automated access.

## Telegram push notifications (recommended)

1. Install Telegram on your phone. In Telegram, open the verified **@BotFather**, send `/newbot`, choose a name and username ending in `bot`, and copy the token. **Never share the token publicly.**
2. Open your new bot and send `/start`. In a browser open `https://api.telegram.org/bot<TOKEN>/getUpdates` (replace `<TOKEN>` locally). Find `message.chat.id` in the JSON response. If the result is empty, send another message to your bot and retry. Do not share this URL or token.
3. To test locally on Linux (run from the project folder):
   ```bash
   export TELEGRAM_BOT_TOKEN='your_bot_token'
   export TELEGRAM_CHAT_ID='your_chat_id'
   python3 job_alert.py
   ```
4. For scheduled GitHub Actions, create **repository secrets** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` under **Settings → Secrets and variables → Actions → New repository secret**. Run the workflow manually from the Actions tab first. Enable Telegram notifications on your phone.

Telegram takes priority over SMTP if both are configured. The bot only sends new matching listings. A score is a simple ranking heuristic, not a probability of acceptance. The public feeds cover a limited subset of employers; adding company-specific feeds is a separate step. GitHub Actions scheduled runs can be delayed.

**Security note:** The existing workflow commits `seen_jobs.sqlite3` to the repository for deduplication. Use a private repository if you do not want the list of encountered job URLs to be public. Never commit tokens.
