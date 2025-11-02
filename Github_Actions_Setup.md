# GitHub Actions Setup Guide

This guide will help you set up automated daily surf alerts using GitHub Actions.

## What This Does

- Runs automatically every day at 6:00 PM Madrid time
- Checks surf conditions for tomorrow
- Sends you an email if waves exceed your threshold
- Completely free (GitHub Actions is free for public repos)

## Setup Steps

### 1. Create GitHub Repository

```bash
cd Surf-Alert-App
git init
git add .
git commit -m "Initial commit: Surf alert app"
```

Create a new repo on GitHub, then:
```bash
git remote add origin https://github.com/YOUR-USERNAME/surf-alert-app.git
git branch -M main
git push -u origin main
```

### 2. Add GitHub Secrets

Your email credentials need to be stored as **GitHub Secrets** (encrypted, never visible in logs).

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these three secrets:

| Name | Value |
|------|-------|
| `SURF_ALERT_EMAIL` | `your-email@gmail.com` |
| `SURF_ALERT_PASSWORD` | `your-16-char-app-password` |
| `SURF_ALERT_RECIPIENT` | `your-email@gmail.com` |

### 3. Enable GitHub Actions

1. Go to your repository on GitHub
2. Click the **Actions** tab
3. If prompted, click **"I understand my workflows, go ahead and enable them"**

### 4. Verify Workflow File

Make sure this file exists in your repo:
```
.github/workflows/surf-alert.yml
```

### 5. Test It Manually

1. Go to **Actions** tab
2. Click **Daily Surf Alert** workflow
3. Click **Run workflow** → **Run workflow**
4. Watch it run (takes ~30 seconds)
5. Check your email!

### 6. Adjust Schedule (Optional)

Edit `.github/workflows/surf-alert.yml`:

```yaml
schedule:
  - cron: '0 17 * * *'  # Change this time
```

**Cron format:** `minute hour day month weekday`

Examples:
- `0 17 * * *` = 5:00 PM UTC daily (6:00 PM CET winter, 7:00 PM CEST summer)
- `0 16 * * *` = 4:00 PM UTC daily
- `30 18 * * *` = 6:30 PM UTC daily
- `0 9 * * 1-5` = 9:00 AM UTC on weekdays only

**Note:** GitHub Actions uses UTC time. Madrid is UTC+1 (winter) or UTC+2 (summer).

## How to View Logs

1. Go to **Actions** tab on GitHub
2. Click on any workflow run
3. Click **check-surf** job
4. See the output (surf conditions, email status, etc.)

## Benefits

✅ **Free** - No cost for public repos
✅ **Reliable** - Runs even when your computer is off
✅ **No maintenance** - GitHub handles everything
✅ **Secure** - Credentials stored as encrypted secrets
✅ **Logs** - See every run in the Actions tab

## Troubleshooting

**Workflow not running:**
- Check if Actions are enabled in repo settings
- Verify the workflow file is in `.github/workflows/` directory
- Check the cron schedule is correct

**Email not sending:**
- Verify secrets are set correctly (no typos)
- Check the workflow logs in Actions tab
- Make sure EMAIL_ENABLED is True in config.py

**Wrong time:**
- Remember GitHub uses UTC time
- Adjust cron schedule accounting for your timezone

## Manual Testing

You can always trigger the workflow manually:
1. Go to Actions tab
2. Select "Daily Surf Alert"
3. Click "Run workflow"
4. Click the green "Run workflow" button

This is great for testing before waiting for the scheduled time!