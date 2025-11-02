#!/usr/bin/env python3
"""
Surf Alert App with Email Notifications
For Vilassar de Mar / Montgat
"""

import requests
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import (
    SURF_THRESHOLD, LOCATION_LAT, LOCATION_LON,
    EMAIL_ENABLED, SMTP_SERVER, SMTP_PORT,
    SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL
)

# All configuration is now in config.py - edit that file to customize settings

def get_surf_forecast():
    """
    Fetch surf forecast using Open-Meteo Marine API (free, no API key needed)
    Returns tomorrow's forecast data
    """
    try:
        # Open-Meteo Marine Weather API
        url = "https://marine-api.open-meteo.com/v1/marine"
        
        params = {
            'latitude': LOCATION_LAT,
            'longitude': LOCATION_LON,
            'hourly': 'wave_height,wave_direction,wave_period,wind_wave_height,wind_wave_direction,wind_wave_period',
            'timezone': 'Europe/Madrid',
            'forecast_days': 3
        }
        
        # Also try to get wind data from regular weather API
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            'latitude': LOCATION_LAT,
            'longitude': LOCATION_LON,
            'hourly': 'wind_speed_10m,wind_direction_10m',
            'timezone': 'Europe/Madrid',
            'forecast_days': 3
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Get wind data
        try:
            wind_response = requests.get(weather_url, params=weather_params, timeout=10)
            wind_response.raise_for_status()
            wind_data = wind_response.json()
            
            # Merge wind data into main data
            if 'hourly' in wind_data:
                data['hourly']['wind_speed_10m'] = wind_data['hourly']['wind_speed_10m']
                data['hourly']['wind_direction_10m'] = wind_data['hourly']['wind_direction_10m']
        except:
            # Wind data is optional
            pass
        
        return data
        
    except Exception as e:
        print(f"Error fetching surf data: {e}")
        return None

def analyze_forecast(data):
    """
    Analyze the forecast data for tomorrow and check if conditions meet alert criteria
    """
    if not data or 'hourly' not in data:
        return None
    
    hourly = data['hourly']
    times = hourly['time']
    wave_heights = hourly['wave_height']
    wave_directions = hourly.get('wave_direction', [None] * len(times))
    wave_periods = hourly.get('wave_period', [None] * len(times))
    wind_speeds = hourly.get('wind_speed_10m', [None] * len(times))
    wind_directions = hourly.get('wind_direction_10m', [None] * len(times))
    
    # Get tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    
    # Filter data for tomorrow
    alerts = []
    max_wave_height = 0
    
    for i, time_str in enumerate(times):
        time_obj = datetime.fromisoformat(time_str)
        
        if time_obj.date() == tomorrow:
            wave_height = wave_heights[i]
            
            if wave_height is not None:
                max_wave_height = max(max_wave_height, wave_height)
                
                if wave_height >= SURF_THRESHOLD:
                    alerts.append({
                        'time': time_obj.strftime('%H:%M'),
                        'wave_height': wave_height,
                        'wave_direction': wave_directions[i] if i < len(wave_directions) and wave_directions[i] is not None else 'N/A',
                        'wave_period': wave_periods[i] if i < len(wave_periods) and wave_periods[i] is not None else 'N/A',
                        'wind_speed': wind_speeds[i] if i < len(wind_speeds) and wind_speeds[i] is not None else 'N/A',
                        'wind_direction': wind_directions[i] if i < len(wind_directions) and wind_directions[i] is not None else 'N/A'
                    })
    
    if alerts:
        return {
            'date': tomorrow.strftime('%Y-%m-%d'),
            'max_wave_height': max_wave_height,
            'alerts': alerts
        }
    
    return None

def degrees_to_compass(degrees):
    """
    Convert degrees to compass direction (N, NE, E, SE, S, SW, W, NW)
    """
    if degrees is None or degrees == 'N/A':
        return 'N/A'
    
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    
    # Normalize to 0-360
    degrees = degrees % 360
    
    # Calculate index (16 directions, so 360/16 = 22.5 degrees each)
    index = int((degrees + 11.25) / 22.5)
    index = index % 16
    
    return directions[index]

def format_alert_message(alert_data):
    """
    Format the alert message
    """
    if not alert_data:
        return "No surf alerts for tomorrow. Wave height below threshold."
    
    message = f"""
🏄 SURF ALERT for {alert_data['date']} 🏄
Location: Vilassar de Mar / Montgat

Maximum Wave Height: {alert_data['max_wave_height']:.2f}m

Good surfing conditions at these times:
"""
    
    for alert in alert_data['alerts']:
        wave_dir = f"{alert['wave_direction']:.0f}° ({degrees_to_compass(alert['wave_direction'])})" if isinstance(alert['wave_direction'], (int, float)) else alert['wave_direction']
        wave_per = f"{alert['wave_period']:.1f}s" if isinstance(alert['wave_period'], (int, float)) else alert['wave_period']
        wind_dir = f"{alert['wind_direction']:.0f}° ({degrees_to_compass(alert['wind_direction'])})" if isinstance(alert['wind_direction'], (int, float)) else alert['wind_direction']
        wind_spd = f"{alert['wind_speed']:.1f} km/h" if isinstance(alert['wind_speed'], (int, float)) else alert['wind_speed']
        
        message += f"\n⏰ {alert['time']}"
        message += f"\n   Wave: {alert['wave_height']:.2f}m from {wave_dir}, period {wave_per}"
        message += f"\n   Wind: {wind_spd} from {wind_dir}"
        message += "\n"
    
    return message

def send_email_notification(subject, message):
    """
    Send email notification
    """
    if not EMAIL_ENABLED:
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject
        
        msg.attach(MIMEText(message, 'plain'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        
        print("✅ Email notification sent successfully!")
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def main():
    """
    Main function to check surf conditions and send alerts
    """
    print(f"Checking surf conditions for Vilassar de Mar / Montgat...")
    print(f"Alert threshold: {SURF_THRESHOLD}m\n")
    
    # Get forecast
    forecast_data = get_surf_forecast()
    
    if forecast_data is None:
        print("Failed to retrieve forecast data")
        return
    
    # Analyze for alerts
    alert_data = analyze_forecast(forecast_data)
    
    # Format message
    message = format_alert_message(alert_data)
    print(message)
    
    # Send notification if conditions are good
    if alert_data and EMAIL_ENABLED:
        subject = f"🏄 Surf Alert: {alert_data['max_wave_height']:.1f}m waves tomorrow!"
        send_email_notification(subject, message)
    elif alert_data and not EMAIL_ENABLED:
        print("\n📧 Email notifications disabled. Set EMAIL_ENABLED = True in config.py to receive alerts.")
    
    return alert_data

if __name__ == "__main__":
    main()