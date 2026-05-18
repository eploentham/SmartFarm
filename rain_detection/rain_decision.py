#!/usr/bin/env python3
"""
Rain Decision Service - WITH DECISION DATABASE LOGGING
======================================================
Reads t_detect_rain table and decides if it's "TRULY RAINING"
(based on 6 consecutive rain records = 3 minutes).

Saves the decision to t_rain_decision table for analysis.

Logic:
  - Reads last 6 records from t_detect_rain
  - If ALL 6 = rain -> TRULY RAINING
  - Otherwise -> NOT raining
  - Logs every decision to t_rain_decision
  - Publishes to MQTT

Run as systemd service alongside rain_detect_orchard.py
"""

import time
import logging
import os
import json
import mysql.connector
import paho.mqtt.client as mqtt
from datetime import datetime

# =====================================================================
# CONFIG
# =====================================================================

DB_CONFIG = {
    'host': 'localhost',
    'user': 'ekapop',
    'password': 'Ekartc2c51*',  # match mqtt.py exactly
    'database': 'smartfarm'
}

MQTT_BROKER = "192.168.0.253"
MQTT_PORT = 1883
MQTT_TOPIC = "smartfarm/rain_status"
MQTT_CLIENT_ID = "rain_decision_service"

RECORDS_TO_CHECK = 6          # 6 records = 3 minutes at 30s interval
CHECK_INTERVAL = 30           # how often to run the decision (seconds)

SENSOR_DEVICE = "nw01_orchard01_camera_01"

LOG_DIR = "/home/ekapop/smartfarm/logs"
LOG_FILE = "rain_decision.log"

# =====================================================================
# Setup
# =====================================================================

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, LOG_FILE)),
        logging.StreamHandler()
    ]
)


# =====================================================================
# Database - read recent detections
# =====================================================================

def get_recent_rain_records(limit=6):
    """Return list of is_raining values from t_detect_rain (newest first)."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG, connection_timeout=5)
        cursor = conn.cursor()
        sql = """SELECT is_raining 
                 FROM t_detect_rain 
                 WHERE sensor_device = %s
                 ORDER BY id DESC 
                 LIMIT %s"""
        cursor.execute(sql, (SENSOR_DEVICE, limit))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return None

        return [row[0] for row in rows]

    except mysql.connector.Error as e:
        logging.error(f"DB read failed: {e}")
        return None


# =====================================================================
# Database - save decision
# =====================================================================

def save_decision_to_database(truly_raining, records):
    """Insert one row into t_rain_decision."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG, connection_timeout=5)
        cursor = conn.cursor()

        # Convert records list to readable string, e.g. "1,1,0,1,1,1"
        if records is not None:
            pattern_str = ",".join(str(v) for v in records)
            rain_count = sum(records)
            records_checked = len(records)
        else:
            pattern_str = None
            rain_count = 0
            records_checked = 0

        sql = """INSERT INTO t_rain_decision
                 (truly_raining, rain_count, records_checked, 
                  recent_pattern, sensor_device)
                 VALUES (%s, %s, %s, %s, %s)"""
        values = (
            1 if truly_raining else 0,
            rain_count,
            records_checked,
            pattern_str,
            SENSOR_DEVICE
        )
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()

    except mysql.connector.Error as e:
        logging.error(f"DB save (decision) failed: {e}")
    except Exception as e:
        logging.error(f"Unexpected DB error: {e}")


# =====================================================================
# Decision logic
# =====================================================================

def decide_truly_raining(is_raining_list):
    """Apply the 3-minute rule. Safe default: False."""
    if is_raining_list is None:
        logging.warning("No data available - defaulting to NOT raining")
        return False

    if len(is_raining_list) < RECORDS_TO_CHECK:
        logging.info(f"Only {len(is_raining_list)} records "
                     f"(need {RECORDS_TO_CHECK}) - NOT raining yet")
        return False

    return all(v == 1 for v in is_raining_list)


# =====================================================================
# MQTT
# =====================================================================

def setup_mqtt():
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        logging.info(f"MQTT connected to {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        logging.error(f"MQTT connect failed: {e}")
    return client


def publish_status(client, truly_raining, recent_data):
    payload = {
        "truly_raining": truly_raining,
        "sensor_device": SENSOR_DEVICE,
        "timestamp": datetime.now().isoformat(),
        "recent_records": recent_data,
        "records_required": RECORDS_TO_CHECK
    }
    try:
        result = client.publish(MQTT_TOPIC, json.dumps(payload),
                                qos=1, retain=True)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logging.warning(f"MQTT publish returned code {result.rc}")
    except Exception as e:
        logging.error(f"MQTT publish failed: {e}")


# =====================================================================
# Main loop
# =====================================================================

def main():
    logging.info("Rain Decision Service started (with DB logging)")
    logging.info(f"Rule: {RECORDS_TO_CHECK} consecutive rain records "
                 f"= {RECORDS_TO_CHECK * 30}s = TRULY RAINING")
    logging.info(f"Sensor: {SENSOR_DEVICE}")

    mqtt_client = setup_mqtt()
    last_decision = None

    while True:
        try:
            records = get_recent_rain_records(RECORDS_TO_CHECK)
            truly_raining = decide_truly_raining(records)

            # Save the decision to database (every cycle)
            save_decision_to_database(truly_raining, records)

            # Loud log only on state change
            if truly_raining != last_decision:
                if truly_raining:
                    logging.info("=" * 50)
                    logging.info(">>> STATE CHANGE: TRULY RAINING <<<")
                    logging.info(f"Last {RECORDS_TO_CHECK} records: {records}")
                    logging.info("=" * 50)
                else:
                    logging.info("=" * 50)
                    logging.info(">>> STATE CHANGE: NOT raining (or stopped) <<<")
                    logging.info(f"Last {RECORDS_TO_CHECK} records: {records}")
                    logging.info("=" * 50)
                last_decision = truly_raining
            else:
                status = "RAINING" if truly_raining else "dry"
                logging.info(f"{status} | recent: {records}")

            publish_status(mqtt_client, truly_raining, records)

        except Exception as e:
            logging.exception(f"Decision loop error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")