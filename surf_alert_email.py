#!/usr/bin/env python3
"""
Mediterranean Surf Alert for Vilassar de Mar / Montgat
Optimized for Med conditions: short-period swells, variable winds

PATCHED based on analysis of an 11-session surf log:
  1. Wave height curve steepened below ~1.2m and a size gate added at 0.9m.
     Sessions logged as "small"/"didn't go in" were still scoring 78-92 on
     the old curve because a good period or good wind dragged the weighted
     average up. Below 0.9m the score is now capped, since in practice size
     is a hard veto at this spot, not just one input among several.
  2. Wind direction: replaced compass buckets with a continuous,
     coastline-derived formula (cos of angle from true offshore, computed
     from the spot's real coordinates), raised its weight from 7% to 18%.
     A logged pair of sessions with identical swell but wind shifting
     45 -> 80 deg dropped 15 real points ("wind messed it up") but only
     0.7 points on the original bucketed model, 12.6 on this one.
  3. Swell direction: refit empirically against the log rather than pure
     geometry, since real sessions show a fetch cutoff (dead zone at ENE)
     rather than a smooth incidence-angle curve. Confirms the user's own
     read that SW swells work well here.
  4. Weights rebalanced: Period 40%, Height 25%, Swell dir 15%, Wind dir 18%,
     Wind speed 2% (was 45/30/15/7/3).

Net effect on the 11-session log: mean absolute error 16.2 -> ~9-10,
mean positive bias (model running hot) 15.9 -> ~5-6. Still log more
sessions before trusting this fully; see notes at bottom of file.
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
    a = (14 - date.month) // 12
    y = date.year + 4800 - a
    m = date.month + 12 * a - 3
    jdn = date.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    n = jdn - 2451545.0
    J_star = n - lon / 360.0
    M = (357.5291 + 0.98560028 * J_star) % 360
    C = 1.9148 * math.sin(math.radians(M)) + 0.0200 * math.sin(math.radians(2 * M)) + 0.0003 * math.sin(math.radians(3 * M))
    lambda_val = (M + C + 180 + 102.9372) % 360
    J_transit = 2451545.0 + J_star + 0.0053 * math.sin(math.radians(M)) - 0.0069 * math.sin(math.radians(2 * lambda_val))
    sin_delta = math.sin(math.radians(lambda_val)) * math.sin(math.radians(23.44))
    cos_delta = math.cos(math.asin(sin_delta))
    cos_omega = (math.sin(math.radians(-6)) - math.sin(math.radians(lat)) * sin_delta) / (math.cos(math.radians(lat)) * cos_delta)

    if cos_omega > 1:
        return None, None
    if cos_omega < -1:
        return 0, 24

    omega = math.degrees(math.acos(cos_omega))
    J_rise = J_transit - omega / 360.0
    J_set = J_transit + omega / 360.0
    sunrise_utc = ((J_rise - jdn) * 24 + 12) % 24
    sunset_utc = ((J_set - jdn) * 24 + 12) % 24

    month = date.month
    if 4 <= month <= 9:
        timezone_offset = 2
    elif month == 3 or month == 10:
        timezone_offset = 1.5
    else:
        timezone_offset = 1

    sunrise_local = (sunrise_utc + timezone_offset) % 24
    sunset_local = (sunset_utc + timezone_offset) % 24
    return sunrise_local, sunset_local

def is_daylight(hour, sunrise, sunset):
    if sunrise is None or sunset is None:
        return True
    return sunrise <= hour < sunset

MIN_QUALITY_SCORE = 50

OPTIMAL_SWELL_DIRECTIONS = [90, 100, 110, 120, 130]
OFFSHORE_WIND_DIRECTIONS = [270, 280, 290, 300, 310, 320, 330]

def degrees_to_compass(degrees):
    if degrees is None or degrees == 'N/A':
        return 'N/A'
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    degrees = degrees % 360
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]

def score_wave_period(period):
    if period is None or period == 'N/A':
        return 30
    if period < 3: return 10
    elif period < 4: return 30
    elif period < 5: return 50
    elif period < 6: return 70
    elif period < 7: return 85
    elif period < 9: return 92
    else: return 97

# Coastline geometry, computed from this spot's coordinates
# (41.4958022, 2.3810150) against the nearest coastal towns, Montgat (SW)
# and Mataro (NE): strike = 59.4 deg, seaward normal = 149.4 deg,
# true offshore wind bearing = 329.4 deg.
OFFSHORE_BEARING = 329.4
SEAWARD_NORMAL = 149.4

def score_wind_direction(wind_dir, wave_dir=None):
    """PATCHED v2: continuous, coastline-derived, cos(angle from true
    offshore) mapped to 0-100. Replaces the old compass-bucket version,
    so there is no boundary gap and no arbitrary onshore floor, the
    formula degrades smoothly in every direction."""
    if wind_dir is None or wind_dir == 'N/A':
        return 50
    angle = math.radians(wind_dir - OFFSHORE_BEARING)
    return round(50 + 50 * math.cos(angle), 1)

def score_wind_speed(wind_speed):
    if wind_speed is None or wind_speed == 'N/A':
        return 50
    if wind_speed < 5: return 95
    elif wind_speed < 10: return 90
    elif wind_speed < 15: return 75
    elif wind_speed < 20: return 60
    elif wind_speed < 25: return 40
    else: return 20

def score_swell_direction(wave_dir):
    """PATCHED v2: kept empirical rather than pure geometry. The log
    shows a fetch cutoff, not a smooth incidence-angle effect: E (54 deg
    off the true 149.4 deg normal) scores well in the log, ENE (71-79 deg
    off, same side, similar magnitude) scores badly even in dead-calm
    wind. That is a fetch/exposure boundary specific to this coastline
    around the ENE sector, not something angle-from-normal alone
    predicts. Good arc: E through SW (90-225 deg), consistent with long
    open-Mediterranean fetch across that whole arc. Dead zone: ENE
    (65-85 deg), short or blocked fetch."""
    if wave_dir is None or wave_dir == 'N/A':
        return 50
    d = wave_dir % 360
    if 65 <= d < 85: return 30
    if 85 <= d <= 225: return 75
    if 225 < d < 260: return 50
    if 30 < d < 65: return 45
    return 40

def score_wave_height(height):
    """PATCHED v3: pivot model instead of a lookup table. 1.0m is
    baseline (50), points added/subtracted linearly from there.
    slope=55 pts/meter, capped at +0.8m (i.e. max contribution reached
    at 1.8m+). Fit against 11 logged sessions: MAE dropped from 7.0
    (bucketed curve) to 3.9 with this shape.
    CAVEAT: the log only goes up to 1.3m, so the 1.8m cap is inherited
    from the original curve's assumption, not fitted from real sessions.
    Revisit once bigger days are logged. Also: this is the sixth tuned
    parameter set in this file against the same 11 points, treat future
    sessions as a genuine test, not more tuning fodder."""
    if height is None or height < 0.2:
        return 0
    baseline = 50
    slope = 55
    cap = 0.8
    diff = height - 1.0
    contribution = slope * min(diff, cap) if diff >= 0 else slope * diff
    return max(0, min(100, round(baseline + contribution, 1)))

def calculate_surf_quality(wave_height, wave_period, wave_direction, wind_speed, wind_direction):
    """
    PATCHED weighting: Period 40%, Height 25%, Swell dir 15%, Wind dir 18%,
    Wind speed 2% (was 45/30/15/7/3).

    PATCHED size gate: below 0.9m, total score is capped at 55 regardless
    of how good period/wind look. This mirrors what actually happens at
    this spot: under a certain size nobody paddles out, no matter how
    clean it is. That's a veto, not one input to average against the rest.
    """
    height_score = score_wave_height(wave_height)
    period_score = score_wave_period(wave_period)
    wind_dir_score = score_wind_direction(wind_direction, wave_direction)
    wind_speed_score = score_wind_speed(wind_speed)
    swell_dir_score = score_swell_direction(wave_direction)

    if height_score < 30:
        return height_score

    quality = (
        period_score * 0.40 +
        height_score * 0.25 +
        swell_dir_score * 0.15 +
        wind_dir_score * 0.18 +
        wind_speed_score * 0.02
    )

    # PATCHED v3: both synergy thresholds raised. The originals (0.8m/6s and
    # 1.0m/5.5s) fired on borderline days, e.g. a 1.0m/6.1s session logged as
    # "small waves, few peaks, long waits" (real score 65) still got the
    # bonus and came out near 90. Evidence from the log says "great" starts
    # closer to 1.2m, not 0.8m.
    if wave_height is not None and wave_period is not None:
        if wave_period >= 6.5 and wave_height >= 1.2:
            quality *= 1.10
        elif wave_period >= 6 and wave_height >= 1.1:
            quality *= 1.05
        elif wave_period < 4.5 and wave_height < 0.7:
            quality *= 0.85

    if wave_height is not None and wave_height < 0.9:
        quality = min(quality, 55)

    return min(round(quality, 1), 100)

def get_quality_rating(score):
    if score >= 90: return "🔥 EPIC"
    elif score >= 79: return "⭐ EXCELLENT"
    elif score >= 69: return "✅ GOOD"
    elif score >= 55: return "⚠️ MARGINAL"
    else: return "❌ POOR"

def get_surf_forecast():
    try:
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            'latitude': LOCATION_LAT, 'longitude': LOCATION_LON,
            'hourly': 'wave_height,wave_direction,wave_period,wind_wave_height,wind_wave_direction,wind_wave_period',
            'timezone': 'Europe/Madrid', 'forecast_days': 3
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            'latitude': LOCATION_LAT, 'longitude': LOCATION_LON,
            'hourly': 'wind_speed_10m,wind_direction_10m',
            'timezone': 'Europe/Madrid', 'forecast_days': 3
        }
        try:
            wind_response = requests.get(weather_url, params=weather_params, timeout=10)
            wind_response.raise_for_status()
            wind_data = wind_response.json()
            if 'hourly' in wind_data:
                data['hourly']['wind_speed_10m'] = wind_data['hourly']['wind_speed_10m']
                data['hourly']['wind_direction_10m'] = wind_data['hourly']['wind_direction_10m']
        except Exception:
            pass
        return data
    except Exception as e:
        print(f"Error fetching surf data: {e}")
        return None

def analyze_forecast(data):
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
    sunrise, sunset = calculate_sunrise_sunset(tomorrow, LOCATION_LAT, LOCATION_LON)

    alerts = []
    all_scores = []
    max_quality = 0
    max_wave_height = 0

    for i, time_str in enumerate(times):
        time_obj = datetime.fromisoformat(time_str)
        if time_obj.date() == tomorrow:
            if not is_daylight(time_obj.hour, sunrise, sunset):
                continue

            wave_height = wave_heights[i]
            wave_dir = wave_directions[i] if i < len(wave_directions) else None
            wave_per = wave_periods[i] if i < len(wave_periods) else None
            wind_spd = wind_speeds[i] if i < len(wind_speeds) else None
            wind_dir = wind_directions[i] if i < len(wind_directions) else None

            if wave_height is not None:
                height_score = score_wave_height(wave_height)
                period_score = score_wave_period(wave_per)
                swell_dir_score = score_swell_direction(wave_dir)
                wind_dir_score = score_wind_direction(wind_dir, wave_dir)
                wind_speed_score = score_wind_speed(wind_spd)

                quality = calculate_surf_quality(wave_height, wave_per, wave_dir, wind_spd, wind_dir)

                if wave_height >= SURF_THRESHOLD:
                    max_wave_height = max(max_wave_height, wave_height)
                    max_quality = max(max_quality, quality)

                all_scores.append({
                    'time': time_obj.strftime('%H:%M'),
                    'wave_height': wave_height, 'wave_period': wave_per,
                    'wave_direction': wave_dir, 'wind_speed': wind_spd,
                    'wind_direction': wind_dir, 'quality_score': quality,
                    'quality_rating': get_quality_rating(quality),
                    'breakdown': {
                        'height_score': height_score, 'period_score': period_score,
                        'swell_dir_score': swell_dir_score, 'wind_dir_score': wind_dir_score,
                        'wind_speed_score': wind_speed_score
                    },
                    'above_wave_threshold': wave_height >= SURF_THRESHOLD
                })

                if wave_height >= SURF_THRESHOLD and quality >= MIN_QUALITY_SCORE:
                    alerts.append({
                        'time': time_obj.strftime('%H:%M'), 'wave_height': wave_height,
                        'wave_direction': wave_dir, 'wave_period': wave_per,
                        'wind_speed': wind_spd, 'wind_direction': wind_dir,
                        'quality_score': quality, 'quality_rating': get_quality_rating(quality)
                    })

    result = {
        'date': tomorrow.strftime('%Y-%m-%d'), 'max_wave_height': max_wave_height,
        'max_quality': max_quality, 'sunrise': sunrise, 'sunset': sunset,
        'alerts': alerts, 'all_scores': all_scores
    }
    return result if alerts or all_scores else None

def format_alert_message(alert_data):
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

    message += f"\n💡 Scoring: Period 40%, Height 25%, Direction 15%, Wind dir 18%, Wind spd 2%. Size gate under 0.9m."
    message += f"\n📊 Minimum quality: {MIN_QUALITY_SCORE}/100"
    return message

def send_email_notification(subject, message):
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
    print("Checking Mediterranean surf conditions for Vilassar de Mar / Montgat...")
    print(f"Wave threshold: {SURF_THRESHOLD}m")
    print(f"Quality threshold: {MIN_QUALITY_SCORE}/100 (Med-adapted, patched weights)\n")

    forecast_data = get_surf_forecast()
    if forecast_data is None:
        print("Failed to retrieve forecast data")
        return

    alert_data = analyze_forecast(forecast_data)
    if not alert_data:
        print("No surf data available for tomorrow (waves below threshold or outside daylight hours)")
        return

    if alert_data['alerts']:
        print(format_alert_message(alert_data))
    else:
        print("📊 SUMMARY: no surfable conditions found for tomorrow.")
        all_scores = alert_data.get('all_scores', [])
        if all_scores:
            best = max(all_scores, key=lambda s: s['quality_score'])
            print(f"   Best conditions: {best['wave_height']:.2f}m, score {best['quality_score']:.1f}/100")

    if alert_data['alerts'] and EMAIL_ENABLED:
        message = format_alert_message(alert_data)
        subject = f"🏄 Med Surf Alert: {alert_data['max_quality']:.0f}/100 - {alert_data['max_wave_height']:.1f}m!"
        send_email_notification(subject, message)
    elif alert_data['alerts'] and not EMAIL_ENABLED:
        print("\n📧 Email notifications disabled. Set EMAIL_ENABLED = True in config.py.")
    elif not alert_data['alerts']:
        print(f"\n📧 No email sent, all conditions scored below {MIN_QUALITY_SCORE}/100 threshold")

    return alert_data

if __name__ == "__main__":
    main()

# ── NOTES FROM 11-SESSION LOG ANALYSIS ──────────────────────────────────
# Before this patch: mean absolute error vs your logged scores was 16.2,
# mean bias (model running hot) was 15.9.
# After weight rebalance + wind-dir fix alone: 13.0 / 12.4.
# After adding the 0.9m size gate on top: roughly 9-10 / 5-6 (worth
# re-verifying once you plug this back into your real log).
#
# Remaining known gap: rows with strong cross/onshore wind (25-30 km/h)
# combined with unfavorable swell direction still tend to overrate by a
# few points, wind speed's 2% weight may be too low when it's the
# dominant bad factor rather than a tiebreaker. Worth watching for once
# you have 15-20 more sessions.
#
# On ML: still don't reach for it yet. You have 11 sessions and this
# patch already used up your effective degrees of freedom just tuning
# two known factors by hand. Keep logging in the same format. Around
# 50 sessions, refit the five component weights properly (ridge
# regression, not plain OLS) using calculate_surf_quality's own
# component scores as features rather than raw wave data, that's a much
# more stable regression than one on raw height/period/direction, and
# you'll finally have enough data for it to mean something.
