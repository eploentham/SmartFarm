#!/usr/bin/env python3
"""
fetch_open_meteo.py
Fetches weather data from Open-Meteo API for the Thong Pha Phum orchard
and logs to MariaDB. Runs hourly via systemd timer.

API: free, no API key required.
Location: 14.755135, 98.646364 (Thong Pha Phum, Kanchanaburi)
"""
import requests
import pymysql
import logging
import os
import sys
from datetime import datetime

# ─── Setup logging ───
LOG_DIR = '/home/ekapop/smartfarm/logs'
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/open_meteo.log'),
        logging.StreamHandler()
    ]
)

# ─── Config ───
ORCHARD_LAT = 14.755135
ORCHARD_LON = 98.646364

DB_CONFIG = {
    'host':       'localhost',  # Replace with your actual MariaDB host IP
    'user':       'ekapop',
    'password':   'Ekartc2c51*',   # TODO: move to .env file
    'database':   'smartfarm',
    'charset':    'utf8mb4',
    'autocommit': True,
}

API_URL = "https://api.open-meteo.com/v1/forecast"
API_PARAMS = {
    'latitude':  ORCHARD_LAT,
    'longitude': ORCHARD_LON,
    'hourly': ','.join([
        'shortwave_radiation',
        'direct_radiation',
        'diffuse_radiation',
        'cloud_cover',
        'temperature_2m',
        'relative_humidity_2m',
        'et0_fao_evapotranspiration',
        'precipitation',
        'wind_speed_10m',
        'wind_direction_10m',
        'wind_gusts_10m',
    ]),
    'daily': ','.join([
        'sunrise', 'sunset',
        'shortwave_radiation_sum',
        'et0_fao_evapotranspiration',
        'precipitation_sum',
        'uv_index_max',
        'wind_speed_10m_max', 
        'wind_gusts_10m_max',  
        'wind_direction_10m_dominant', 
    ]),
    'timezone':      'Asia/Bangkok',
    'forecast_days': 3,
    'past_days':     1,    # also get yesterday's actuals
}


def fetch_weather() -> dict | None:
    """Fetch weather data from Open-Meteo. Returns parsed JSON dict or None on failure."""
    try:
        response = requests.get(API_URL, params=API_PARAMS, timeout=30)
        response.raise_for_status()
        data = response.json()
        logging.info(
            f"Fetched OK. Grid cell at ({data['latitude']}, {data['longitude']}), "
            f"elevation {data.get('elevation', '?')}m"
        )
        return data
    except requests.RequestException as e:
        logging.error(f"API fetch failed: {e}")
        return None


def upsert_hourly(conn, data: dict) -> int:
    """Insert/update hourly records. Returns row count."""
    hourly = data.get('hourly', {})
    times = hourly.get('time', [])
    if not times:
        logging.warning("No hourly data in response")
        return 0

    sql = """
        INSERT INTO t_weather_open_meteo_hourly
            (record_time, shortwave_radiation, direct_radiation, diffuse_radiation,
             cloud_cover, temperature_2m, relative_humidity_2m,
             et0_fao, precipitation,
             wind_speed_10m, wind_direction_10m, wind_gusts_10m,
             is_forecast)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            shortwave_radiation   = VALUES(shortwave_radiation),
            direct_radiation      = VALUES(direct_radiation),
            diffuse_radiation     = VALUES(diffuse_radiation),
            cloud_cover           = VALUES(cloud_cover),
            temperature_2m        = VALUES(temperature_2m),
            relative_humidity_2m  = VALUES(relative_humidity_2m),
            et0_fao               = VALUES(et0_fao),
            precipitation         = VALUES(precipitation),
            wind_speed_10m        = VALUES(wind_speed_10m),
            wind_direction_10m    = VALUES(wind_direction_10m),
            wind_gusts_10m        = VALUES(wind_gusts_10m),
            is_forecast           = VALUES(is_forecast),
            fetched_at            = CURRENT_TIMESTAMP
    """

    now = datetime.now()
    rows = []
    for i, t in enumerate(times):
        record_time = datetime.fromisoformat(t)
        rows.append((
            record_time,
            hourly['shortwave_radiation'][i],
            hourly['direct_radiation'][i],
            hourly['diffuse_radiation'][i],
            hourly['cloud_cover'][i],
            hourly['temperature_2m'][i],
            hourly['relative_humidity_2m'][i],
            hourly['et0_fao_evapotranspiration'][i],
            hourly['precipitation'][i],
            hourly['wind_speed_10m'][i],
            hourly['wind_direction_10m'][i],
            hourly['wind_gusts_10m'][i],
            record_time > now,   # future = forecast, past = actual
        ))

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    logging.info(f"Upserted {len(rows)} hourly rows")
    return len(rows)


def upsert_daily(conn, data: dict) -> int:
    """Insert/update daily aggregates. Returns row count."""
    daily = data.get('daily', {})
    times = daily.get('time', [])
    if not times:
        return 0

    sql = """
        INSERT INTO t_weather_open_meteo_daily
            (record_date, shortwave_radiation_sum, et0_fao_sum,
             precipitation_sum, uv_index_max,
             wind_speed_max, wind_gusts_max, wind_direction_dominant,
             sunrise, sunset, is_forecast)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            shortwave_radiation_sum  = VALUES(shortwave_radiation_sum),
            et0_fao_sum              = VALUES(et0_fao_sum),
            precipitation_sum        = VALUES(precipitation_sum),
            uv_index_max             = VALUES(uv_index_max),
            wind_speed_max           = VALUES(wind_speed_max),
            wind_gusts_max           = VALUES(wind_gusts_max),
            wind_direction_dominant  = VALUES(wind_direction_dominant),
            sunrise                  = VALUES(sunrise),
            sunset                   = VALUES(sunset),
            is_forecast              = VALUES(is_forecast),
            fetched_at               = CURRENT_TIMESTAMP
    """

    today = datetime.now().date()
    rows = []
    for i, d_str in enumerate(times):
        record_date = datetime.fromisoformat(d_str).date()
        sunrise_t = datetime.fromisoformat(daily['sunrise'][i]).time()
        sunset_t  = datetime.fromisoformat(daily['sunset'][i]).time()

        rows.append((
            record_date,
            daily['shortwave_radiation_sum'][i],
            daily['et0_fao_evapotranspiration'][i],
            daily['precipitation_sum'][i],
            daily['uv_index_max'][i],
            daily['wind_speed_10m_max'][i],
            daily['wind_gusts_10m_max'][i],
            daily['wind_direction_10m_dominant'][i],
            sunrise_t,
            sunset_t,
            record_date > today,
        ))

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    logging.info(f"Upserted {len(rows)} daily rows")
    return len(rows)


def main():
    data = fetch_weather()
    if not data:
        sys.exit(1)

    try:
        conn = pymysql.connect(**DB_CONFIG)
        upsert_hourly(conn, data)
        upsert_daily(conn, data)
        conn.close()
        logging.info("Done")
    except pymysql.MySQLError as e:
        logging.error(f"DB error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()