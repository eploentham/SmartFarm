# คำแนะนำการติดตั้งและการตั้งค่าระบบตรวจจับฝนด้วย Raspberry Pi 5

## การติดตั้งซอฟต์แวร์ที่จำเป็น

1. ติดตั้ง Raspberry Pi OS ล่าสุดบน SD Card
2. เชื่อมต่อ Raspberry Pi กับอินเทอร์เน็ต
3. เปิด Terminal และติดตั้งแพ็คเกจที่จำเป็น:

```bash
# อัปเดตระบบ
sudo apt update
sudo apt upgrade -y

# ติดตั้งไลบรารีที่จำเป็น
sudo apt install -y python3-opencv python3-pip git

# ติดตั้ง Picamera2
sudo apt install -y python3-picamera2

# ติดตั้งไลบรารี Python เพิ่มเติม
pip3 install numpy
```

## การเชื่อมต่อกล้อง

### สำหรับ Raspberry Pi Camera Module:

1. ปิดเครื่อง Raspberry Pi
2. เชื่อมต่อกล้องเข้ากับพอร์ตกล้องบน Raspberry Pi 5
3. เปิดเครื่อง Raspberry Pi
4. เปิดใช้งานกล้องโดยใช้คำสั่ง:

```bash
sudo raspi-config
```

เลือก Interface Options -> Camera -> เปิดใช้งาน -> Finish

### สำหรับกล้อง USB:

1. เสียบกล้อง USB เข้ากับพอร์ต USB ของ Raspberry Pi
2. ตรวจสอบว่ากล้องถูกตรวจพบโดยใช้คำสั่ง:

```bash
ls -l /dev/video*
```

## การติดตั้งโค้ด

1. สร้างโฟลเดอร์สำหรับโปรเจค:

```bash
mkdir -p ~/rain_detection
cd ~/rain_detection
```

2. สร้างไฟล์ Python โดยใช้คำสั่ง:

```bash
nano rain_detector.py
```

3. คัดลอกโค้ดจากไฟล์ "โค้ดตรวจจับฝนตกด้วย Raspberry Pi 5" ไปวางในไฟล์ rain_detector.py
4. บันทึกไฟล์โดยกด Ctrl+X, Y, Enter

## การติดตั้งกล้องและ Raspberry Pi

1. ติดตั้ง Raspberry Pi และกล้องในจุดที่เหมาะสม โดยหันกล้องไปทางระเบียงที่สามารถเห็นน้ำฝนหยดได้
2. ตรวจสอบให้แน่ใจว่ามีแหล่งจ่ายไฟที่เหมาะสม
3. ปรับมุมกล้องให้เหมาะสม (ในระยะแรกอาจต้องทดลองปรับมุมหลายครั้ง)

## การทดสอบระบบ

1. รันโปรแกรมด้วยคำสั่ง:

```bash
python3 rain_detector.py
```

2. ทดสอบโดยใช้น้ำจากหลอดฉีดน้ำหรือขวดฉีดน้ำเพื่อจำลองฝนตก
3. ตรวจสอบไฟล์ล็อกและภาพที่บันทึกในโฟลเดอร์ rain_images

## การตั้งค่าให้ทำงานอัตโนมัติเมื่อเปิดเครื่อง

1. สร้างไฟล์ service ของ systemd:

```bash
sudo nano /etc/systemd/system/rain-detector.service
```

2. ใส่เนื้อหาต่อไปนี้:

```
[Unit]
Description=Rain Detection System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/rain_detection/rain_detector.py
WorkingDirectory=/home/pi/rain_detection
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

3. บันทึกไฟล์และออกจากตัวแก้ไข (Ctrl+X, Y, Enter)
4. เปิดใช้และเริ่มต้น service:

```bash
sudo systemctl enable rain-detector.service
sudo systemctl start rain-detector.service
```

5. ตรวจสอบสถานะของ service:

```bash
sudo systemctl status rain-detector.service
```

## การปรับแต่งพารามิเตอร์

หากต้องการปรับแต่งความไวในการตรวจจับ สามารถแก้ไขค่าพารามิเตอร์ต่อไปนี้ในไฟล์ rain_detector.py:

- `motion_threshold`: ค่าความแตกต่างขั้นต่ำที่ถือว่ามีการเคลื่อนไหว (เพิ่มค่าเพื่อลดความไว)
- `rain_threshold`: จำนวนการเคลื่อนไหวขั้นต่ำที่ถือว่าฝนตก (เพิ่มค่าเพื่อลดผลบวกปลอม)
- `droplet_min_size` และ `droplet_max_size`: ขนาดของหยดน้ำที่จะตรวจจับ

## การแก้ไขปัญหาเบื้องต้น

### กล้องไม่ทำงาน

1. ตรวจสอบการเชื่อมต่อสายกล้อง
2. สำหรับกล้อง USB ให้ตรวจสอบด้วยคำสั่ง `ls -l /dev/video*`
3. สำหรับ Pi Camera ให้ตรวจสอบว่าได้เปิดใช้งานในการตั้งค่า raspi-config

### ระบบตรวจจับผิดพลาด (ผลบวกปลอม)

1. ปรับค่า `motion_threshold` และ `rain_threshold` ให้สูงขึ้น
2. ปรับค่า ROI โดยแก้ไขค่า `self.roi_y` ในโค้ด

### CPU ใช้งานสูงเกินไป

1. เพิ่มค่า `time.sleep()` ในลูป `while` ของฟังก์ชัน `run()`
2. ลดขนาดภาพในการตั้งค่ากล้อง `config = self.camera.create_still_configuration(main={"size": (640, 480)})`