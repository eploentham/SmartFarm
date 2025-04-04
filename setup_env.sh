#!/bin/bash
#chmod +x setup_env.sh      ทำให้ script สามารถรันได้       ./setup_env.sh
# สร้างโฟลเดอร์สำหรับโปรเจค
mkdir -p smartfarm
cd smartfarm

# สร้าง logs directory
mkdir -p logs

# ตรวจสอบว่ามี python3-venv หรือยัง
if ! dpkg -l | grep -q python-venv; then
    echo "Installing python-venv..."
    sudo apt update
    sudo apt install -y python-venv
fi

# สร้าง virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# เปิดใช้งาน virtual environment
source venv/bin/activate

# อัพเกรด pip
echo "Upgrading pip..."
pip install --upgrade pip

# ติดตั้ง packages ที่จำเป็น
echo "Installing required packages..."
pip install paho-mqtt mysql-connector-python ntplib pytz

# สร้างไฟล์ requirements.txt
echo "Creating requirements.txt..."
pip freeze > requirements.txt

# สร้าง activate.sh สำหรับเปิดใช้ environment ในครั้งต่อไป
echo "Creating activation script..."
cat > activate.sh << 'EOL'
#!/bin/bash
source venv/bin/activate
EOL
chmod +x activate.sh

# แสดงคำแนะนำ
echo "
Virtual environment setup complete!

To activate the environment:
    source venv/bin/activate
    or
    ./activate.sh

To deactivate:
    deactivate

Your project structure:
    smartfarm/
    ├── venv/           (virtual environment)
    ├── logs/           (for log files)
    ├── requirements.txt (package list)
    └── activate.sh     (activation script)

Next steps:
1. Copy your Python scripts into this directory
2. Activate the virtual environment
3. Run your scripts

Example:
    ./activate.sh
    python mqtt.py
"