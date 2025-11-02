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
import math

def calculate_sunrise_sunset(date, lat, lon):
    """
    Calculate sunrise and sunset times for a given date and location
    Uses civil twilight (-6°) which is when there's enough light to surf
    Returns (sunrise_hour, sunset_hour) in 24h format as floats
    """
    # Julian day calculation
    a = (14 - date.month) // 12
    y = date.year + 4800 - a
    m = date.month + 12 * a - 3
    jdn = date.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    
    # Number of days since Jan 1, 2000 12:00
    n = jdn - 2451545.0
    
    # Mean solar time
    J_star = n - lon / 360.0
    
    # Solar mean anomaly
    M = (357.5291 + 0.98560028 * J_star) % 360
    
    # Equation of center
    C = 1.9148 * math.sin(math.radians(M)) + 0.0200 * math.sin(math.radians(2 * M)) + 0.0003 * math.sin(math.radians(3 * M))
    
    # Ecliptic longitude
    lambda_val = (M + C + 180 + 102.9372) % 360
    
    # Solar transit
    J_transit = 2451545.0 + J_star + 0.0053 * math.sin(math.radians(M)) - 0.0069 * math.sin(math.radians(2 * lambda_val))
    
    # Declination of the sun
    sin_delta = math.sin(math.radians(lambda_val)) * math.sin(math.radians(23.44))
    cos_delta = math.cos(math.asin(sin_delta))
    
    # Hour angle - using -6° for civil twilight (enough light to see and surf)
    cos_omega = (math.sin(math.radians(-6)) - math.sin(math.radians(lat)) * sin_delta) / (math.cos(math.radians(lat)) * cos_delta)
    
    # Handle polar day/night
    if cos_omega > 1:
        return None, None  # Polar night
    if cos_omega < -1:
        return 0, 24  # Polar day
    
    omega = math.degrees(math.acos(cos_omega))
    
    # Sunrise and sunset in Julian days
    J_rise = J_transit - omega / 360.0
    J_set = J_transit + omega / 360.0
    
    # Convert to hours (UTC)
    sunrise_utc = ((J_rise - jdn) * 24 + 12) % 24
    sunset_utc = ((J_set - jdn) * 24 + 12) % 24
    
    # Convert to local time
    # Spain is UTC+1 (CET) in winter, UTC+2 (CEST) in summer
    # Approximate DST: last Sunday of March to last Sunday of October
    month = date.month
    if 4 <= month <= 9:  # Roughly April to September
        timezone_offset = 2  # CEST (summer)
    elif month == 3 or month == 10:
        timezone_offset = 1.5  # Transition months, use 1.5 as approximation
    else:
        timezone_offset = 1  # CET (winter)
    
    sunrise_local = (sunrise_utc + timezone_offset) % 24
    sunset_local = (sunset_utc + timezone_offset) % 24
    
    return sunrise_local, sunset_local

def is_daylight(hour, sunrise, sunset):
    """Check if given hour is during daylight"""
    if sunrise is None or sunset is None:
        return True  # If can't calculate, include all hours
    return sunrise <= hour < sunset

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
    Short period = weak, choppy waves - be realistic!
    """
    if period is None or period == 'N/A':
        return 30  # Unknown, assume poor
    
    if period < 3:
        return 10  # Useless chop
    elif period < 4:
        return 30  # Very short, weak - hard to ride
    elif period < 5:
        return 50  # Short but starting to work
    elif period < 6:
        return 70  # Decent for Med
    elif period < 7:
        return 85  # Good for Med
    elif period < 9:
        return 92  # Very good for Med - rare!
    else:
        return 97  # Epic for Med - very rare groundswell

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
    
    Natural weighting - no artificial caps:
    - Wave Period (45%) - MOST important: weak chop vs powerful waves
    - Wave Height (30%) - Must have rideable size
    - Swell Direction (15%) - Does it hit the beach?
    - Wind Direction (7%) - Clean vs choppy
    - Wind Speed (3%) - Glassy bonus
    
    With 45% weight, short period naturally kills the score:
    - 0.6m @ 3.9s perfect conditions = ~45 points (weak)
    - 1.0m @ 6s good conditions = ~80 points (good!)
    """
    # Calculate individual scores
    height_score = score_wave_height(wave_height)
    period_score = score_wave_period(wave_period)
    wind_dir_score = score_wind_direction(wind_direction, wave_direction)
    wind_speed_score = score_wind_speed(wind_speed)
    swell_dir_score = score_swell_direction(wave_direction)
    
    # Minimum viable waves
    if height_score < 30:
        return height_score  # Too small
    
    # Natural weighted combination - period dominates
    quality = (
        period_score * 0.45 +      # PERIOD IS KING - determines wave power
        height_score * 0.30 +       # Size matters but period matters more
        swell_dir_score * 0.15 +    # Direction
        wind_dir_score * 0.07 +     # Wind direction
        wind_speed_score * 0.03     # Wind speed
    )
    
    # Synergy bonuses for truly good combos
    if wave_height is not None and wave_period is not None:
        # Powerful waves: good period + good size
        if wave_period >= 6 and wave_height >= 0.8:
            quality *= 1.10  # 10% bonus
        elif wave_period >= 5.5 and wave_height >= 1.0:
            quality *= 1.05  # 5% bonus
        # Weak combo: short period + small size
        elif wave_period < 4.5 and wave_height < 0.7:
            quality *= 0.85  # 15% penalty
    
    return min(round(quality, 1), 100)

def get_quality_rating(score):
    """Convert numeric score to text rating - adjusted for Med"""
    if score >= 80:
        return "🔥 EPIC (for Med!)"
    elif score >= 70:
        return "⭐ EXCELLENT"
    elif score >= 60:
        return "✅ GOOD"
    elif score >= 50:
        return "👍 FAIR - Worth checking"
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
    """Analyze forecast with Med-adapted quality scoring - daylight hours only"""
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
    
    # Calculate sunrise/sunset for tomorrow
    sunrise, sunset = calculate_sunrise_sunset(tomorrow, LOCATION_LAT, LOCATION_LON)
    
    alerts = []
    all_scores = []  # Track all scores for logging
    max_quality = 0
    max_wave_height = 0
    
    for i, time_str in enumerate(times):
        time_obj = datetime.fromisoformat(time_str)
        
        if time_obj.date() == tomorrow:
            # Only include daylight hours
            if not is_daylight(time_obj.hour, sunrise, sunset):
                continue
            
            wave_height = wave_heights[i]
            wave_dir = wave_directions[i] if i < len(wave_directions) else None
            wave_per = wave_periods[i] if i < len(wave_periods) else None
            wind_spd = wind_speeds[i] if i < len(wind_speeds) else None
            wind_dir = wind_directions[i] if i < len(wind_directions) else None
            
            # Log ALL daylight hours, even if wave height is below threshold or None
            if wave_height is not None:
                # Calculate individual component scores for logging
                height_score = score_wave_height(wave_height)
                period_score = score_wave_period(wave_per)
                swell_dir_score = score_swell_direction(wave_dir)
                wind_dir_score = score_wind_direction(wind_dir, wave_dir)
                wind_speed_score = score_wind_speed(wind_spd)
                
                # Calculate quality score
                quality = calculate_surf_quality(
                    wave_height, wave_per, wave_dir, wind_spd, wind_dir
                )
                
                # Track max values only for waves above threshold
                if wave_height >= SURF_THRESHOLD:
                    max_wave_height = max(max_wave_height, wave_height)
                    max_quality = max(max_quality, quality)
                
                # Store ALL scores for logging (even below wave height threshold)
                all_scores.append({
                    'time': time_obj.strftime('%H:%M'),
                    'wave_height': wave_height,
                    'wave_period': wave_per,
                    'wave_direction': wave_dir,
                    'wind_speed': wind_spd,
                    'wind_direction': wind_dir,
                    'quality_score': quality,
                    'quality_rating': get_quality_rating(quality),
                    'breakdown': {
                        'height_score': height_score,
                        'period_score': period_score,
                        'swell_dir_score': swell_dir_score,
                        'wind_dir_score': wind_dir_score,
                        'wind_speed_score': wind_speed_score
                    },
                    'above_wave_threshold': wave_height >= SURF_THRESHOLD
                })
                
                # Only add to alerts if meets BOTH thresholds
                if wave_height >= SURF_THRESHOLD and quality >= MIN_QUALITY_SCORE:
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
    
    # Return data including all scores for logging
    result = {
        'date': tomorrow.strftime('%Y-%m-%d'),
        'max_wave_height': max_wave_height,
        'max_quality': max_quality,
        'sunrise': sunrise,
        'sunset': sunset,
        'alerts': alerts,
        'all_scores': all_scores  # Include all scores for detailed logging
    }
    
    return result if alerts or all_scores else None

def format_alert_message(alert_data):
    """Format the alert message with quality scores"""
    if not alert_data:
        return f"No quality surf alerts for tomorrow (minimum score: {MIN_QUALITY_SCORE}/100 for Med conditions)."
    
    sunrise = alert_data.get('sunrise')
    sunset = alert_data.get('sunset')
    
    sunrise_str = f"{int(sunrise):02d}:{int((sunrise % 1) * 60):02d}" if sunrise else "N/A"
    sunset_str = f"{int(sunset):02d}:{int((sunset % 1) * 60):02d}" if sunset else "N/A"
    
    message = f"""🏄 SURF ALERT for {alert_data['date']} 🏄
Location: Vilassar de Mar / Montgat

🌅 Sunrise: {sunrise_str} | Sunset: {sunset_str} 🌇
Maximum Wave Height: {alert_data['max_wave_height']:.2f}m
Peak Quality Score: {alert_data['max_quality']:.0f}/100 {get_quality_rating(alert_data['max_quality'])}

Surfable windows (daylight hours only):
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
    
    message += f"\n💡 Natural scoring (no caps): Period 45%, Height 30%, Direction 15%, Wind 10%"
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
    
    if not alert_data:
        print("No surf data available for tomorrow (waves below threshold or outside daylight hours)")
        return
    
    # Print detailed scoring breakdown for all time slots
    print("=" * 80)
    print("DETAILED SCORING BREAKDOWN (all daylight hours)")
    print("=" * 80)
    
    # Display sunrise/sunset times
    sunrise = alert_data.get('sunrise')
    sunset = alert_data.get('sunset')
    if sunrise and sunset:
        sunrise_str = f"{int(sunrise):02d}:{int((sunrise % 1) * 60):02d}"
        sunset_str = f"{int(sunset):02d}:{int((sunset % 1) * 60):02d}"
        print(f"\n🌅 First Light: {sunrise_str} | Last Light: {sunset_str} 🌇")
    
    all_scores = alert_data.get('all_scores', [])
    if all_scores:
        print(f"\nScoring formula: Period(45%) + Height(30%) + Direction(15%) + Wind Dir(7%) + Wind Spd(3%)\n")
        
        for score_data in all_scores:
            breakdown = score_data['breakdown']
            time = score_data['time']
            quality = score_data['quality_score']
            rating = score_data['quality_rating']
            
            wave_h = score_data['wave_height']
            wave_p = score_data.get('wave_period', 'N/A')
            wave_d = score_data.get('wave_direction', 'N/A')
            wind_s = score_data.get('wind_speed', 'N/A')
            wind_d = score_data.get('wind_direction', 'N/A')
            
            wave_p_str = f"{wave_p:.1f}s" if isinstance(wave_p, (int, float)) else wave_p
            wave_d_str = f"{wave_d:.0f}°" if isinstance(wave_d, (int, float)) else wave_d
            wind_s_str = f"{wind_s:.1f} km/h" if isinstance(wind_s, (int, float)) else wind_s
            wind_d_str = f"{wind_d:.0f}°" if isinstance(wind_d, (int, float)) else wind_d
            
            # Show both thresholds
            above_wave_threshold = score_data.get('above_wave_threshold', False)
            wave_status = "✅ Above 0.5m" if above_wave_threshold else "❌ Below 0.5m"
            quality_status = "✅ ALERT" if quality >= MIN_QUALITY_SCORE else "❌ Below quality threshold"
            
            print(f"{time} → Score: {quality:.1f}/100 {rating}")
            print(f"  {wave_status} | {quality_status}")
            print(f"  Conditions: {wave_h:.2f}m @ {wave_p_str} from {wave_d_str}, wind {wind_s_str} from {wind_d_str}")
            print(f"  Calculation:")
            print(f"    Period score:     {breakdown['period_score']:.0f}/100 × 45% = {breakdown['period_score'] * 0.45:.1f}")
            print(f"    Height score:     {breakdown['height_score']:.0f}/100 × 30% = {breakdown['height_score'] * 0.30:.1f}")
            print(f"    Direction score:  {breakdown['swell_dir_score']:.0f}/100 × 15% = {breakdown['swell_dir_score'] * 0.15:.1f}")
            print(f"    Wind dir score:   {breakdown['wind_dir_score']:.0f}/100 × 7%  = {breakdown['wind_dir_score'] * 0.07:.1f}")
            print(f"    Wind speed score: {breakdown['wind_speed_score']:.0f}/100 × 3%  = {breakdown['wind_speed_score'] * 0.03:.1f}")
            print(f"    Total: {quality:.1f}/100")
            print()
    
    print("=" * 80)
    print()
    
    # Print formatted message
    message = format_alert_message(alert_data)
    print(message)
    
    # Send email if alerts exist
    if alert_data['alerts'] and EMAIL_ENABLED:
        subject = f"🏄 Med Surf Alert: {alert_data['max_quality']:.0f}/100 - {alert_data['max_wave_height']:.1f}m!"
        send_email_notification(subject, message)
    elif alert_data['alerts'] and not EMAIL_ENABLED:
        print("\n📧 Email notifications disabled. Set EMAIL_ENABLED = True in config.py.")
    elif not alert_data['alerts']:
        print(f"\n📧 No email sent - all conditions scored below {MIN_QUALITY_SCORE}/100 threshold")
    
    return alert_data

if __name__ == "__main__":
    main()