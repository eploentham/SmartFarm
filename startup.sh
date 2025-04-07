#!/bin/bash
# Navigate to the project directory
#chmod +x startup.sh
cd /home/ekapop/smartfarm
# Activate virtual environment
source /home/ekapop/smartfarm/bin/activate
# Start mqtt.py in the background   
python /home/ekapop/smartfarm/mqtt.py &
# Navigate to digital_clock directory and start digital_clock.py in the background
cd /home/ekapop/smartfarm/digital_clock
python /home/ekapop/smartfarm/digital_clock.py