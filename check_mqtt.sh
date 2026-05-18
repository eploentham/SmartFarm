#!/bin/bash
echo "=== สถานะ Process ==="
if pgrep -f "mqtt.py" > /dev/null; then
    echo "✓ mqtt.py กำลังทำงาน (PID: $(pgrep -f mqtt.py))"
else
    echo "✗ mqtt.py ไม่ได้ทำงาน"
fi

echo ""
echo "=== Log ล่าสุด 10 บรรทัด ==="
tail -n 10 /home/ekapop/smartfarm/logs/mqtt.log

echo ""
echo "=== ข้อมูลล่าสุดใน Database ==="
mysql -u root -pEkartc2c51* smartfarm -e \
    "SELECT id, temperature, humidity, sensor_device, created_at 
     FROM t_sensor ORDER BY id DESC LIMIT 5;" 2>/dev/null

echo ""
echo "=== MQTT Broker ทดสอบเชื่อมต่อ ==="
timeout 3 mosquitto_sub -h 192.168.0.253 -t smartfarm/temperature -C 1 2>&1