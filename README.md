# Surf Alert App for Vilassar de Mar / Montgat

A simple Python script that checks surf conditions and alerts you when wave heights exceed your threshold.

## Features

- ✅ Checks wave height, wave direction, wave period, and wind conditions
- ✅ Sends alerts the day before when surf conditions are good
- ✅ Uses free Open-Meteo Marine API (no API key required)
- ✅ Easy to customize threshold and notification method
- ✅ Displays compass directions (N, NE, E, etc.) alongside degrees

## Requirements

- Python 3.7+
- Internet connection
- Required packages: `requests`

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install requests python-dotenv
```

2. Edit the configuration in `config.py`:
```python
SURF_THRESHOLD = 1.5  # Change to your desired wave height in meters
EMAIL_ENABLED = False  # Set to True for email notifications
```

All settings are now in one place - `config.py`!

## Security - Keeping Email Credentials Private

If you want to push this to GitHub, **DO NOT commit your email credentials**. Here are your options:

### Option 1: Use Environment Variables (Recommended)

**Important:** You must have `python-dotenv` installed for this to work!
```bash
pip install python-dotenv
```

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` with your real credentials:
```
SURF_ALERT_EMAIL=your-email@gmail.com
SURF_ALERT_PASSWORD=your-gmail-app-password
SURF_ALERT_RECIPIENT=your-email@gmail.com
```

3. The script automatically loads from `.env` (thanks to python-dotenv)

4. Run the script:
```bash
python3 surf_alert_email.py
```

The `.gitignore` file already prevents `.env` from being committed!

### Option 2: Keep Repository Private

Simply make your GitHub repo private instead of public. Your credentials will be safe.

### Option 3: Use config_local.py

1. Create `config_local.py` with your real credentials (already in .gitignore)
2. Import from that in your scripts instead
3. Never commit `config_local.py`

### Option 4: Use GitHub Secrets (for GitHub Actions)

If you set up automated runs with GitHub Actions, store credentials as repository secrets.

## Usage

### Manual Check
Run the script manually to check tomorrow's conditions:
```bash
python3 surf_alert.py
```

### Automated Daily Alerts

#### Option 1: GitHub Actions (Recommended - Always On) ☁️

Run automatically in the cloud, even when your computer is off!

See **[GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md)** for complete setup instructions.

Quick steps:
1. Push code to GitHub (public or private repo)
2. Add your email credentials as GitHub Secrets
3. Enable GitHub Actions
4. It runs daily at 6 PM automatically!

**Benefits:**
- ✅ Free for public repos
- ✅ Runs even when your computer is off
- ✅ No maintenance required
- ✅ Secure (credentials encrypted)

#### Option 2: Cron Job (Linux/Mac - Requires Computer On)
Set up a cron job to run daily at 6 PM (requires your computer to be on):

```bash
crontab -e
```

Add this line:
```
0 18 * * * /usr/bin/python3 /path/to/surf_alert.py
```

#### Option 3: Windows Task Scheduler (Requires Computer On)
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 6:00 PM
4. Set action: Start a program
5. Program: `python3`
6. Arguments: `C:\path\to\surf_alert.py`

## Adding Notifications

The script currently prints to console. To receive actual notifications, uncomment and configure one of these methods in `surf_alert.py`:

### Email Notifications
```python
import smtplib
from email.mime.text import MIMEText

def send_email(message):
    msg = MIMEText(message)
    msg['Subject'] = 'Surf Alert!'
    msg['From'] = 'your-email@gmail.com'
    msg['To'] = 'your-email@gmail.com'
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login('your-email@gmail.com', 'your-app-password')
        smtp.send_message(msg)
```

### Telegram Bot
```python
import requests

def send_telegram(message):
    bot_token = 'YOUR_BOT_TOKEN'
    chat_id = 'YOUR_CHAT_ID'
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    requests.post(url, data={'chat_id': chat_id, 'text': message})
```

### SMS (Twilio)
```python
from twilio.rest import Client

def send_sms(message):
    account_sid = 'YOUR_ACCOUNT_SID'
    auth_token = 'YOUR_AUTH_TOKEN'
    client = Client(account_sid, auth_token)
    
    client.messages.create(
        body=message,
        from_='+1234567890',
        to='+1234567890'
    )
```

## How It Works

1. Fetches marine weather data from Open-Meteo API for Vilassar de Mar
2. Analyzes tomorrow's hourly forecast
3. Identifies times when wave height exceeds your threshold
4. Formats an alert with times, wave heights, directions, and wind conditions
5. Sends notification (or prints to console)

## Customization

- **Location**: Edit `LOCATION_LAT` and `LOCATION_LON` in the script
- **Threshold**: Change `SURF_THRESHOLD` to your desired wave height
- **Forecast days**: Modify `forecast_days` parameter in API call
- **Time zone**: Change `timezone` parameter (default: Europe/Madrid)

## Example Output

```
🏄 SURF ALERT for 2025-11-03 🏄
Location: Vilassar de Mar / Montgat

Maximum Wave Height: 1.8m

Good surfing conditions at these times:

⏰ 08:00
   Wave: 1.6m from 120°
   Wind: 15.2 km/h from 90°

⏰ 09:00
   Wave: 1.8m from 125°
   Wind: 16.1 km/h from 95°
```

## Troubleshooting

- **No data received**: Check internet connection
- **Incorrect location**: Verify coordinates are correct
- **No alerts**: Wave height may be below threshold, try lowering it
- **Email not sending - "Username and Password not accepted"**: 
  - Make sure you installed `python-dotenv`: `pip install python-dotenv`
  - Use Gmail App Password (not regular password): https://myaccount.google.com/apppasswords
  - Remove all spaces from the 16-character app password in `.env`
  - Verify `.env` file is in the same directory as the scripts
- **Environment variables show placeholders**: Install `python-dotenv` package

## Data Source

This app uses the [Open-Meteo Marine Weather API](https://open-meteo.com/en/docs/marine-weather-api), which provides free access to marine forecasts without requiring an API key.

## License

Free to use and modify for personal use.