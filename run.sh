#!/bin/bash
#chmod +x run.sh
# เปิดใช้งาน virtual environment
source home/ekapop/smartfarm/bin/activate
# รัน mqtt.py ในพื้นหลัง
python home/ekapop/smartfarm/mqtt.py &
# รัน digital_clock.py
python home/ekapop/smartfarm/digital_clock.py
# เมื่อปิด digital_clock จะปิด mqtt.py ด้วย
pkill -f home/ekapop/smartfarm/mqtt.py