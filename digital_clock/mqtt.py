import paho.mqtt.client as mqtt
import json
import mysql.connector
from datetime import datetime
import logging
import os

# สร้างโฟลเดอร์ logs ถ้ายังไม่มี
if not os.path.exists('logs'):
    os.makedirs('logs')

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mqtt.log'),
        logging.StreamHandler()
    ]
)

# MariaDB configuration
db_config = {
    'host': 'localhost',
    'user': 'ekapop',  # แก้เป็น username ของ MariaDB
    'password': 'Ekartc2c51*',  # แก้เป็น password ของ MariaDB
    'database': 'smartfarm'
}

# MQTT configuration 
mqtt_broker = "192.168.100.242"  # แก้เป็น IP ของ MQTT broker
mqtt_port = 1883
mqtt_topic = "smartfarm/temperature"

def connect_to_database():
    """เชื่อมต่อกับฐานข้อมูล MariaDB"""
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        logging.error(f"Error connecting to database: {err}")
        return None

def save_to_database(data):
    """บันทึกข้อมูลลงฐานข้อมูล"""
    conn = connect_to_database()
    if conn is None:
        return
    
    try:
        cursor = conn.cursor()
        sql = """INSERT INTO t_sensor 
                (temperature, humidity, sensor_device) 
                VALUES (%s, %s, %s)"""
        values = (
            data['temperature'],
            data['humidity'],
            data['sensor_device']
        )
        cursor.execute(sql, values)
        conn.commit()
        logging.info(f"Saved data: Temperature={data['temperature']}, Humidity={data['humidity']}, Sensor={data['sensor_device']}")
    except mysql.connector.Error as err:
        logging.error(f"Error saving data: {err}")
    finally:
        cursor.close()
        conn.close()

def on_connect(client, userdata, flags, rc):
    """Callback เมื่อเชื่อมต่อ MQTT สำเร็จ"""
    if rc == 0:
        logging.info("Connected to MQTT broker successfully")
        client.subscribe(mqtt_topic)
        logging.info(f"Subscribed to topic: {mqtt_topic}")
    else:
        logging.error(f"Failed to connect to MQTT broker with code: {rc}")

def on_message(client, userdata, msg):
    """Callback เมื่อได้รับข้อความจาก MQTT"""
    try:
        payload = json.loads(msg.payload.decode())
        logging.info(f"Received MQTT message: {payload}")
        
        # ตรวจสอบว่ามีข้อมูลครบถ้วน
        required_fields = ['temperature', 'humidity', 'sensor_device']
        if all(field in payload for field in required_fields):
            save_to_database(payload)
        else:
            logging.warning(f"Incomplete data received: {payload}")
            
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")
    except Exception as e:
        logging.error(f"Error processing message: {e}")

def on_disconnect(client, userdata, rc):
    """Callback เมื่อขาดการเชื่อมต่อ MQTT"""
    if rc != 0:
        logging.warning("Unexpected MQTT disconnection. Will auto-reconnect")

def main():
    """ฟังก์ชันหลักสำหรับรัน MQTT client"""
    # ตั้งค่า MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # พยายามเชื่อมต่อ MQTT broker
    try:
        logging.info(f"Connecting to MQTT broker at {mqtt_broker}:{mqtt_port}")
        client.connect(mqtt_broker, mqtt_port, 60)
        
        # เริ่ม loop
        logging.info("Starting MQTT loop...")
        client.loop_forever()
        
    except Exception as e:
        logging.error(f"Error in MQTT connection: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Program terminated by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")