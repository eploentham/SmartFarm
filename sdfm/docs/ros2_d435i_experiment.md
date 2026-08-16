# DR01 ROS 2 D435i proof of concept

This experiment is perception-only. Keep the Pixhawk **DISARMED**, remove the
propellers where practical, and do not run ARM, TAKEOFF, or motor commands.
The existing direct `pyrealsense2` path remains unchanged.

## Supported baseline

First inspect `pi5-drone1`; do not infer its OS from this repository:

```bash
cat /etc/os-release
uname -m
printenv ROS_DISTRO
ros2 --version
```

For Ubuntu 24.04 (Noble) on Raspberry Pi 5 (`arm64`), use ROS 2 Jazzy. If the
host is Ubuntu 22.04, stop and review the deployment rather than mixing Jazzy
packages into that OS (Humble is the native 22.04 ROS distribution). Verify
available packages before installing anything:

```bash
apt-cache policy ros-jazzy-ros-base ros-jazzy-realsense2-camera
```

Installation is intentionally not automated by SDFM. Follow the official ROS
2 apt setup, then install only the experiment dependencies:

```bash
sudo apt update
sudo apt install ros-jazzy-ros-base ros-jazzy-realsense2-camera ros-jazzy-rosbag2
source /opt/ros/jazzy/setup.bash
```

Do not install a second librealsense by another method over a working package
set. If the arm64 wrapper package is unavailable for the configured repository,
build the official `realsense-ros` wrapper in a separate colcon workspace; do
not copy its source or business logic into SDFM.

## Bring up and discover actual topics

Terminal 1:

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch realsense2_camera rs_launch.py camera_namespace:=dr01 camera_name:=d435i
```

Terminal 2 (record the actual output; names can vary with driver parameters):

```bash
source /opt/ros/jazzy/setup.bash
ros2 node list
ros2 topic list -t
ros2 topic list -t | grep 'sensor_msgs/msg/Image'
ros2 topic info --verbose ACTUAL_DEPTH_TOPIC
ros2 topic hz ACTUAL_DEPTH_TOPIC
```

Confirm that `ACTUAL_DEPTH_TOPIC` has type `sensor_msgs/msg/Image` and encoding
`16UC1` or `32FC1` (for example with `ros2 topic echo ... --once`). Then run the
SDFM subscriber from the directory that contains the `sdfm` package:

```bash
cd ~/smartfarm
source /opt/ros/jazzy/setup.bash
python3 -m sdfm.ros.nodes.depth_subscriber --ros-args \
  -p depth_topic:=ACTUAL_DEPTH_TOPIC
```

The terminal reports nearest (5th percentile), median, valid-pixel ratio, and
the existing `ObstacleDetector` state. Ctrl-C cleanly stops either process. A
missing/disconnected stream produces `DEPTH_STREAM_UNAVAILABLE` and no command
is sent to MAVLink.

## Record and replay the same walk

Use a descriptive, bounded output directory and include camera info with depth:

```bash
mkdir -p ~/smartfarm/data/rosbags
cd ~/smartfarm/data/rosbags
ros2 bag record -o dr01_d435i_walk_YYYYMMDD \
  ACTUAL_DEPTH_TOPIC ACTUAL_DEPTH_CAMERA_INFO_TOPIC
```

Stop recording with Ctrl-C. Inspect and replay with the physical camera driver
stopped:

```bash
ros2 bag info ~/smartfarm/data/rosbags/dr01_d435i_walk_YYYYMMDD
ros2 bag play ~/smartfarm/data/rosbags/dr01_d435i_walk_YYYYMMDD --loop
```

Start the same subscriber against the recorded topic. ROS bag playback uses
the same adapter and core detector, enabling repeatable A/B algorithm tests.

## Safe validation checklist

1. `ros2 node list` works and reports the RealSense node.
2. `rs-enumerate-devices` detects the D435i.
3. The driver starts without USB errors.
4. `ros2 topic hz` is stable near the configured rate.
5. The SDFM subscriber reports frames continuously.
6. Known objects at measured distances produce plausible ROI values.
7. A short bag records, reports with `ros2 bag info`, and replays.
8. Disconnecting/stopping D435i yields `DEPTH_STREAM_UNAVAILABLE` safely.
9. Stop ROS and run the unchanged direct test:

   ```bash
   cd ~/smartfarm
   python3 -m sdfm.scripts.test_realsense
   ```

No part of this experiment opens MAVLink, changes ArduPilot parameters, or
changes the direct RC/Pixhawk safety path.
