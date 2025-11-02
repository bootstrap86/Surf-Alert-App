#!/usr/bin/env python3
"""
Mediterranean Surf Alert for Vilassar de Mar / Montgat
Optimized for Med conditions: short-period swells, variable winds
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

# ==================== MEDITERRANEAN SURF CONFIGURATION ====================
# Minimum quality score (0-100) to trigger an alert
MIN_QUALITY_SCORE = 50  # Lower for Med - some swell is better than no swell!

# Spot-specific for Vilassar de Mar / Montgat (based on surf-forecast.com)
# Best swell: East-Southeast (ESE)
# Best wind: Northwest (offshore)
OPTIMAL_SWELL_DIRECTIONS = [90, 100, 110, 120, 130]  # E to ESE (primary direction)
OFFSHORE_WIND_DIRECTIONS = [270, 280, 290, 300, 310, 320, 330]  # W to NW (offshore)

def degrees_to_compass(degrees):
    """Convert degrees to compass direction"""
    if degrees is None or degrees == 'N/A':
        return 'N/A'
    
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    degrees = degrees % 360
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]

def score_wave_period(period):
    """
    Score wave period for MEDITERRANEAN conditions (0-100)
    Med rarely sees 10s+ periods - adjust expectations!
    3-6s is typical wind swell here
    """
    if period is None or period == 'N/A':
        return 40  # Unknown, assume mediocre
    
    if period < 3:
        return 20  # Very short, wind chop
    elif period < 4:
        return 50  # Short but common in Med - rideable!
    elif period < 5:
        return 65  # Decent for Med
    elif period < 6:
        return 75  # Good for Med
    elif period < 7:
        return 85  # Very good for Med
    elif period < 9:
        return 90  # Excellent for Med - rare!
    else:
        return 95  # Epic for Med - very rare groundswell

def score_wind_direction(wind_dir, wave_dir):
    """
    Score wind direction (0-100)
    NW wind (offshore) = best, onshore E/SE = worst
    """
    if wind_dir is None or wind_dir == 'N/A':
        return 50  # Unknown
    
    # Perfect offshore (NW, W)
    if any(abs(wind_dir - d) < 30 for d in OFFSHORE_WIND_DIRECTIONS):
        return 100  # Clean offshore!
    
    # Side-offshore (N, WSW)
    if 330 < wind_dir or wind_dir < 30 or 240 < wind_dir < 270:
        return 80  # Good enough
    
    # Cross-shore (NE, SW, S)
    if 30 < wind_dir < 80 or 180 < wind_dir < 240:
        return 60  # Okay, workable
    
    # Onshore (E, ESE, SE) - same direction as waves
    if 80 < wind_dir < 150:
        return 30  # Choppy, but in Med sometimes you take what you get!
    
    return 50  # Default

def score_wind_speed(wind_speed):
    """
    Score wind speed (0-100)
    Light winds = glassy. In Med, moderate wind often brings the swell!
    """
    if wind_speed is None or wind_speed == 'N/A':
        return 50
    
    if wind_speed < 5:
        return 95  # Glassy perfection
    elif wind_speed < 10:
        return 90  # Light, clean
    elif wind_speed < 15:
        return 75  # Moderate - still good in Med
    elif wind_speed < 20:
        return 60  # Getting choppy but rideable
    elif wind_speed < 25:
        return 40  # Windy, harder to surf
    else:
        return 20  # Too windy

def score_swell_direction(wave_dir):
    """
    Score swell direction (0-100)
    E-ESE is optimal for Vilassar de Mar
    """
    if wave_dir is None or wave_dir == 'N/A':
        return 50
    
    # Perfect direction: E to ESE (90-130°)
    if 85 < wave_dir < 135:
        return 100  # Directly into the beach!
    
    # Good directions: ENE or SE (70-150°)
    if 70 < wave_dir < 150:
        return 85  # Will work well
    
    # Okay directions: NE or S (50-170°)
    if 50 < wave_dir < 170:
        return 65  # Will produce some waves
    
    # Marginal (N or SSW)
    if 30 < wave_dir < 180:
        return 40  # Might get something
    
    return 20  # Wrong direction

def score_wave_height(height):
    """
    Score wave height (0-100)
    This is now a PRIMARY factor, not just a bonus
    """
    if height is None or height < 0.2:
        return 0  # Too small to surf
    elif height < 0.4:
        return 30  # Barely rideable, small fun
    elif height < 0.6:
        return 60  # Small but fun
    elif height < 0.9:
        return 80  # Good size for Med
    elif height < 1.2:
        return 90  # Great size
    elif height < 1.8:
        return 95  # Excellent, pumping!
    elif height < 2.5:
        return 90  # Big but still good
    else:
        return 70  # Too big/dangerous for most

def calculate_surf_quality(wave_height, wave_period, wave_direction, wind_speed, wind_direction):
    """
    Calculate overall surf quality for MEDITERRANEAN conditions (0-100)
    
    Priority hierarchy:
    1. Wave Height (35%) - Must have waves! Most important.
    2. Wave Period (25%) - Determines power and cleanliness
    3. Swell Direction (20%) - Does it hit the beach well?
    4. Wind Direction (15%) - Clean vs choppy
    5. Wind Speed (5%) - Fine-tuning for glassy conditions
    """
    # Calculate individual scores
    height_score = score_wave_height(wave_height)
    period_score = score_wave_period(wave_period)
    wind_dir_score = score_wind_direction(wind_direction, wave_direction)
    wind_speed_score = score_wind_speed(wind_speed)
    swell_dir_score = score_swell_direction(wave_direction)
    
    # If waves are too small, cap the score
    if height_score < 30:
        return height_score  # Nothing else matters if too small
    
    # Weighted combination - HEIGHT IS KING
    # Wave height (35%) - must have rideable waves!
    # Period (25%) - power and wave quality  
    # Swell direction (20%) - optimal angle for the beach
    # Wind direction (15%) - offshore = clean, onshore = choppy
    # Wind speed (5%) - glassy bonus
    quality = (
        height_score * 0.35 +
        period_score * 0.25 +
        swell_dir_score * 0.20 +
        wind_dir_score * 0.15 +
        wind_speed_score * 0.05
    )
    
    # Synergy bonuses for ideal combinations
    # Long period + good height = powerful, clean waves
    if wave_height is not None and wave_period is not None:
        if wave_period >= 6 and wave_height >= 0.8:
            quality *= 1.15  # 15% bonus for powerful combo
        elif wave_period >= 5 and wave_height >= 1.0:
            quality *= 1.08  # 8% bonus
    
    # Perfect direction + good size = extra bonus
    if wave_height is not None and wave_height >= 0.8:
        if 85 < wave_direction < 135:  # Perfect ESE angle
            quality *= 1.05  # 5% bonus for optimal direction with size
    
    # Cap at 100
    return min(round(quality, 1), 100)

def get_quality_rating(score):
    """Convert numeric score to text rating - adjusted for Med"""
    if score >= 80:
        return "⭐⭐⭐⭐⭐ EPIC (for Med!)"
    elif score >= 70:
        return "⭐⭐⭐⭐ EXCELLENT"
    elif score >= 60:
        return "⭐⭐⭐ GOOD"
    elif score >= 50:
        return "⭐⭐ FAIR - Worth checking"
    elif score >= 40:
        return "⚠️ MARGINAL"
    else:
        return "❌ POOR"

def get_surf_forecast():
    """Fetch surf forecast using Open-Meteo Marine API"""
    try:
        url = "https://marine-api.open-meteo.com/v1/marine"
        
        params = {
            'latitude': LOCATION_LAT,
            'longitude': LOCATION_LON,
            'hourly': 'wave_height,wave_direction,wave_period,wind_wave_height,wind_wave_direction,wind_wave_period',
            'timezone': 'Europe/Madrid',
            'forecast_days': 3
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Get wind data
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            'latitude': LOCATION_LAT,
            'longitude': LOCATION_LON,
            'hourly': 'wind_speed_10m,wind_direction_10m',
            'timezone': 'Europe/Madrid',
            'forecast_days': 3
        }
        
        try:
            wind_response = requests.get(weather_url, params=weather_params, timeout=10)
            wind_response.raise_for_status()
            wind_data = wind_response.json()
            
            if 'hourly' in wind_data:
                data['hourly']['wind_speed_10m'] = wind_data['hourly']['wind_speed_10m']
                data['hourly']['wind_direction_10m'] = wind_data['hourly']['wind_direction_10m']
        except:
            pass
        
        return data
        
    except Exception as e:
        print(f"Error fetching surf data: {e}")
        return None

def analyze_forecast(data):
    """Analyze forecast with Med-adapted quality scoring"""
    if not data or 'hourly' not in data:
        return None
    
    hourly = data['hourly']
    times = hourly['time']
    wave_heights = hourly['wave_height']
    wave_directions = hourly.get('wave_direction', [None] * len(times))
    wave_periods = hourly.get('wave_period', [None] * len(times))
    wind_speeds = hourly.get('wind_speed_10m', [None] * len(times))
    wind_directions = hourly.get('wind_direction_10m', [None] * len(times))
    
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    
    alerts = []
    max_quality = 0
    max_wave_height = 0
    
    for i, time_str in enumerate(times):
        time_obj = datetime.fromisoformat(time_str)
        
        if time_obj.date() == tomorrow:
            wave_height = wave_heights[i]
            
            if wave_height is not None and wave_height >= SURF_THRESHOLD:
                wave_dir = wave_directions[i] if i < len(wave_directions) else None
                wave_per = wave_periods[i] if i < len(wave_periods) else None
                wind_spd = wind_speeds[i] if i < len(wind_speeds) else None
                wind_dir = wind_directions[i] if i < len(wind_directions) else None
                
                # Calculate quality score
                quality = calculate_surf_quality(
                    wave_height, wave_per, wave_dir, wind_spd, wind_dir
                )
                
                max_wave_height = max(max_wave_height, wave_height)
                max_quality = max(max_quality, quality)
                
                # Only add if quality meets minimum threshold
                if quality >= MIN_QUALITY_SCORE:
                    alerts.append({
                        'time': time_obj.strftime('%H:%M'),
                        'wave_height': wave_height,
                        'wave_direction': wave_dir,
                        'wave_period': wave_per,
                        'wind_speed': wind_spd,
                        'wind_direction': wind_dir,
                        'quality_score': quality,
                        'quality_rating': get_quality_rating(quality)
                    })
    
    if alerts:
        return {
            'date': tomorrow.strftime('%Y-%m-%d'),
            'max_wave_height': max_wave_height,
            'max_quality': max_quality,
            'alerts': alerts
        }
    
    return None

def format_alert_message(alert_data):
    """Format the alert message with quality scores"""
    if not alert_data:
        return f"No quality surf alerts for tomorrow (minimum score: {MIN_QUALITY_SCORE}/100 for Med conditions)."
    
    message = f"""🏄 SURF ALERT for {alert_data['date']} 🏄
Location: Vilassar de Mar / Montgat

Maximum Wave Height: {alert_data['max_wave_height']:.2f}m
Peak Quality Score: {alert_data['max_quality']:.0f}/100 {get_quality_rating(alert_data['max_quality'])}

Surfable windows (Med-adapted scoring):
"""
    
    for alert in alert_data['alerts']:
        wave_dir = f"{alert['wave_direction']:.0f}° ({degrees_to_compass(alert['wave_direction'])})" if isinstance(alert['wave_direction'], (int, float)) else alert['wave_direction']
        wave_per = f"{alert['wave_period']:.1f}s" if isinstance(alert['wave_period'], (int, float)) else alert['wave_period']
        wind_dir = f"{alert['wind_direction']:.0f}° ({degrees_to_compass(alert['wind_direction'])})" if isinstance(alert['wind_direction'], (int, float)) else alert['wind_direction']
        wind_spd = f"{alert['wind_speed']:.1f} km/h" if isinstance(alert['wind_speed'], (int, float)) else alert['wind_speed']
        
        message += f"\n⏰ {alert['time']} - Quality: {alert['quality_score']:.0f}/100 {alert['quality_rating']}"
        message += f"\n   Wave: {alert['wave_height']:.2f}m from {wave_dir}, period {wave_per}"
        message += f"\n   Wind: {wind_spd} from {wind_dir}"
        message += "\n"
    
    message += f"\n💡 Optimized for Mediterranean conditions (short-period swells 3-6s typical)"
    message += f"\n📊 Minimum quality: {MIN_QUALITY_SCORE}/100"
    return message

def send_email_notification(subject, message):
    """Send email notification"""
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
    """Main function"""
    print(f"Checking Mediterranean surf conditions for Vilassar de Mar / Montgat...")
    print(f"Wave threshold: {SURF_THRESHOLD}m")
    print(f"Quality threshold: {MIN_QUALITY_SCORE}/100 (Med-adapted)\n")
    
    forecast_data = get_surf_forecast()
    
    if forecast_data is None:
        print("Failed to retrieve forecast data")
        return
    
    alert_data = analyze_forecast(forecast_data)
    
    message = format_alert_message(alert_data)
    print(message)
    
    if alert_data and EMAIL_ENABLED:
        subject = f"🏄 Med Surf Alert: {alert_data['max_quality']:.0f}/100 - {alert_data['max_wave_height']:.1f}m!"
        send_email_notification(subject, message)
    elif alert_data and not EMAIL_ENABLED:
        print("\n📧 Email notifications disabled. Set EMAIL_ENABLED = True in config.py.")
    
    return alert_data

if __name__ == "__main__":
    main()