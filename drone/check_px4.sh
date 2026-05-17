#!/bin/bash
echo "=================================================="
echo "     PX4 SITL + ROS 2 Error Checker"
echo "     สำหรับ Durian Drone Project"
echo "=================================================="

echo "Date: $(date)"
echo "Hostname: $(hostname)"
echo

# 1. ตรวจสอบ PX4 Directory
echo "=== 1. PX4 Directory Check ==="
if [ -d ~/PX4-Autopilot ]; then
    echo "✅ พบโฟลเดอร์ PX4-Autopilot"
    cd ~/PX4-Autopilot
    echo "Current branch: $(git branch --show-current)"
else
    echo "❌ ไม่พบโฟลเดอร์ PX4-Autopilot → ยังไม่ได้ clone"
fi
echo

# 2. ตรวจสอบ ROS 2
echo "=== 2. ROS 2 Status ==="
source /opt/ros/jazzy/setup.bash 2>/dev/null
if command -v ros2 &> /dev/null; then
    echo "✅ ROS 2 Jazzy ทำงานปกติ"
    ros2 --version
else
    echo "❌ ไม่พบ ROS 2"
fi
echo

# 3. ตรวจสอบ Dependency ที่พบบ่อย
echo "=== 3. Critical Dependencies ==="
for pkg in kconfiglib pyros-genmsg empy jinja2 colcon; do
    if python3 -c "import $pkg" 2>/dev/null; then
        echo "✅ $pkg → OK"
    else
        echo "❌ $pkg → Missing"
    fi
done
echo

# 4. ตรวจสอบ Gazebo / Simulation
echo "=== 4. Gazebo / Simulation Check ==="
if command -v gz &> /dev/null; then
    echo "✅ Gazebo Harmonic ติดตั้งแล้ว"
    gz --version
else
    echo "❌ ไม่พบ gz (Gazebo)"
fi
echo

# 5. สรุปปัญหาที่พบบ่อย + แนวทางแก้
echo "=================================================="
echo "ปัญหาที่พบบ่อยและวิธีแก้"
echo "=================================================="
echo "1. Gazebo Timeout     → เพิ่ม Swap + ใช้ -j2"
echo "2. kconfiglib missing → pip3 install kconfiglib --break-system-packages"
echo "3. genmsg missing     → pip3 install pyros-genmsg --break-system-packages"
echo "4. Temperature สูง    → ลด arm_freq=1400 + ติดพัดลม"
echo "5. Under-voltage      → ใช้ BEC 5V 5A + Capacitor"
echo
echo "รันคำสั่งนี้เพื่อแก้ dependency อัตโนมัติ:"
echo "   sudo apt install -y python3-pip && pip3 install kconfiglib pyros-genmsg empy jinja2 --break-system-packages"
echo "=================================================="

