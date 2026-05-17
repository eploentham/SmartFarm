#!/bin/bash
echo "=================================================="
echo "     SD Card Storage Monitor - Durian Drone"
echo "=================================================="
echo "Date: $(date)"
echo

echo "=== 1. สรุปพื้นที่ทั้งหมด ==="
df -h / 

echo -e "\n=== 2. โฟลเดอร์ที่กินพื้นที่มากที่สุด (Top 10) ==="
echo "กำลังสแกน... (อาจใช้เวลาสักครู่)"
du -sh /* 2>/dev/null | sort -hr | head -n 10

echo -e "\n=== 3. ในโฟลเดอร์ Home (ekapop) ==="
du -sh /home/ekapop/* 2>/dev/null | sort -hr | head -n 8

echo -e "\n=== 4. ROS 2 Log (กินพื้นที่บ่อย) ==="
du -sh ~/.ros/log 2>/dev/null || echo "ไม่มีโฟลเดอร์ log"

echo -e "\n=== 5. คำแนะนำ ==="
echo "• ถ้า /dev/mmcblk0p2 เต็ม 100% → ต้องล้างด่วน"
echo "• ล้าง ROS Log: rm -rf ~/.ros/log/*"
echo "• ล้าง Cache: sudo apt clean && sudo apt autoremove -y"
echo "• ลบภาพ/วิดีโอเก่าใน ~/durian_images/ หรือ ~/Videos/"
echo "=================================================="
