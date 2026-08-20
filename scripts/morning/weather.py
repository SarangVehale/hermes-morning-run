"""Weather stream — Open-Meteo (free, no auth).

Returns a single-line summary for Pimpri-Chinchwad usable as the `Weather`
section of the Brief and the Dashboard. Plain prose: current temp, high/low,
conditions, and a light dressing hint when relevant. No LLM call — facts only."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

# Pimpri-Chinchwad approx. Override via env if you move.
DEFAULT_LAT = 18.63
DEFAULT_LON = 73.81
TIMEZONE = "Asia/Kolkata"

URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,weather_code,apparent_temperature"
    "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,uv_index_max"
    "&timezone={tz}"
    "&forecast_days=1"
)

# WMO weather codes → short label. India-relevant subset; snow conditions
# included for completeness but practically irrelevant here.
_CODE_LABEL = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains",
    80: "rain showers", 81: "heavy showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm",
}

# WMO code → Unicode glyph (no emoji per HERMES convention — these are Unicode
# weather symbols, not SMP emoji).
_CODE_GLYPH = {
    0: "☀", 1: "🌤", 2: "⛅", 3: "☁",
    45: "🌫", 48: "🌫",
    51: "🌦", 53: "🌧", 55: "🌧",
    56: "🌧", 57: "🌧",
    61: "🌧", 63: "🌧", 65: "🌧",
    66: "🌧", 67: "🌧",
    71: "🌨", 73: "🌨", 75: "🌨", 77: "🌨",
    80: "🌦", 81: "🌧", 82: "⛈",
    85: "🌨", 86: "🌨",
    95: "⛈", 96: "⛈", 99: "⛈",
}


def glyph_for(code: int) -> str:
    return _CODE_GLYPH.get(code, "")


def _fetch(lat: float, lon: float) -> dict | None:
    url = URL.format(lat=lat, lon=lon, tz=TIMEZONE)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-morning/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[weather] fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _hint(code: int, t_max: float, precip: float) -> str:
    if code in (95, 96, 99):
        return "Carry rain gear; thunderstorm risk."
    if code in (61, 63, 65, 80, 81, 82) or precip >= 5:
        return "Carry an umbrella."
    if code in (45, 48):
        return "Reduced visibility — drive carefully."
    if t_max >= 38:
        return "Hot day; stay hydrated, avoid midday sun."
    if t_max >= 33:
        return "Warm; light cotton fine."
    if t_max <= 18:
        return "Cool; a light jacket helps."
    return ""


def summary_line(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> str:
    data = _fetch(lat, lon)
    if not data or "current" not in data or "daily" not in data:
        return "> [!warning] Weather: Open-Meteo unreachable or returned malformed data."

    cur = data["current"]
    daily = data["daily"]
    t_now = round(cur.get("temperature_2m", 0))
    feels = round(cur.get("apparent_temperature", t_now))
    t_max = round(daily.get("temperature_2m_max", [t_now])[0])
    t_min = round(daily.get("temperature_2m_min", [t_now])[0])
    code = int(daily.get("weather_code", [0])[0])
    precip = float(daily.get("precipitation_sum", [0])[0])
    label = _CODE_LABEL.get(code, f"code {code}")

    feels_suffix = f" (feels {feels}°C)" if abs(feels - t_now) >= 2 else ""
    hint = _hint(code, float(t_max), precip)
    hint_suffix = f" {hint}" if hint else ""
    precip_suffix = f" Expected rainfall {precip:.0f} mm." if precip >= 1 else ""

    glyph = _CODE_GLYPH.get(code, "")
    glyph_prefix = f"{glyph} " if glyph else ""
    return (
        f"{glyph_prefix}Pimpri-Chinchwad — {t_now}°C now{feels_suffix}, "
        f"high {t_max}°C / low {t_min}°C, {label}."
        f"{precip_suffix}{hint_suffix}"
    )


def run() -> str:
    """Return the one-line weather summary. No vault write — composer drops it
    directly into the Brief + Dashboard."""
    return summary_line()


if __name__ == "__main__":
    print(run())
