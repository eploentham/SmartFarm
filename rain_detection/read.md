SmartFarm/
├── rain_detection/
│   ├── __init__.py
│   ├── camera.py         # โค้ดสำหรับจัดการกล้อง
│   ├── detector.py       # โค้ดสำหรับตรวจจับฝน
│   └── data_logger.py    # โค้ดสำหรับบันทึกข้อมูล
├── data/
│   ├── logs/            # สำหรับเก็บ log files
│   ├── images/          # สำหรับเก็บรูปภาพ
│   └── records/         # สำหรับเก็บไฟล์ CSV
├── config.py            # ไฟล์ configuration
├── main.py             # ไฟล์หลักสำหรับรันโปรแกรม
└── requirements.txt    # รายการ dependencies
pip install -r requirements.txt