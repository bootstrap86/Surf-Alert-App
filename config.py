"""
Configuration file for Surf Alert App
Edit these settings to customize your alerts
"""

import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Find .env file in the same directory as this script
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    # python-dotenv not installed, will use system environment variables
    pass

# ==================== SURF SETTINGS ====================
# Wave height threshold in meters - you'll get alerts when waves exceed this
SURF_THRESHOLD = 0.5

# Location coordinates for Vilassar de Mar / Montgat
LOCATION_LAT = 41.5089
LOCATION_LON = 2.3944

# ==================== EMAIL SETTINGS ====================
# Set to True to enable email notifications
EMAIL_ENABLED = True

# Gmail SMTP settings
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

# Your email credentials - loaded from environment variables for security
# Set these in your terminal or .env file (see README for instructions)
SENDER_EMAIL = os.getenv('SURF_ALERT_EMAIL', 'your-email@gmail.com')
SENDER_PASSWORD = os.getenv('SURF_ALERT_PASSWORD', 'your-app-password')
RECIPIENT_EMAIL = os.getenv('SURF_ALERT_RECIPIENT', 'your-email@gmail.com')