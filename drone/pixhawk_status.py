from pymavlink import mavutil
import math
import time

PORT = "/dev/ttyACM0"
BAUD = 115200


def connect_pixhawk():
    print(f"Connecting Pixhawk: {PORT}")

    master = mavutil.mavlink_connection(
        PORT,
        baud=BAUD
    )

    print("Waiting for HEARTBEAT...")

    heartbeat = master.wait_heartbeat(timeout=10)

    if heartbeat is None:
        raise TimeoutError("Pixhawk HEARTBEAT timeout")

    print("Pixhawk connected")
    print(f"System ID    : {master.target_system}")
    print(f"Component ID : {master.target_component}")
    print()

    return master


def main():

    master = connect_pixhawk()
    request_message_interval(
    master,
        mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
        1
    )

    request_message_interval(
        master,
        mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
        2
    )

    request_message_interval(
        master,
        mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
        5
    )

    # เก็บค่าล่าสุดที่ได้รับจาก Pixhawk
    status = {
        "mode": "-",
        "armed": False,

        "voltage": None,
        "current": None,
        "battery_remaining": None,

        "gps_fix": None,
        "satellites": None,
        "lat": None,
        "lon": None,

        "roll": None,
        "pitch": None,
        "yaw": None,
    }

    last_print = 0

    while True:
        try:
            # ไม่ใช้ blocking=True
            # เพื่อให้ loop สามารถทำงานอื่นต่อได้
            msg = master.recv_match(blocking=False)

            if msg is not None:

                msg_type = msg.get_type()

                # --------------------------------
                # HEARTBEAT
                # --------------------------------
                if msg_type == "HEARTBEAT":

                    status["armed"] = bool(
                        msg.base_mode
                        & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                    )

                    status["mode"] = mavutil.mode_string_v10(msg)

                # --------------------------------
                # BATTERY
                # --------------------------------
                elif msg_type == "SYS_STATUS":

                    if msg.voltage_battery != 65535:
                        status["voltage"] = (
                            msg.voltage_battery / 1000.0
                        )

                    if msg.current_battery != -1:
                        status["current"] = (
                            msg.current_battery / 100.0
                        )

                    if msg.battery_remaining != -1:
                        status["battery_remaining"] = (
                            msg.battery_remaining
                        )

                # --------------------------------
                # GPS
                # --------------------------------
                elif msg_type == "GPS_RAW_INT":

                    status["gps_fix"] = msg.fix_type
                    status["satellites"] = msg.satellites_visible

                    if msg.lat != 0:
                        status["lat"] = msg.lat / 1e7

                    if msg.lon != 0:
                        status["lon"] = msg.lon / 1e7

                # --------------------------------
                # ATTITUDE
                # --------------------------------
                elif msg_type == "ATTITUDE":

                    status["roll"] = math.degrees(msg.roll)
                    status["pitch"] = math.degrees(msg.pitch)
                    status["yaw"] = math.degrees(msg.yaw)

            # --------------------------------
            # DISPLAY ทุก 1 วินาที
            # --------------------------------

            now = time.time()

            if now - last_print >= 1:

                print("\033[2J\033[H", end="")

                print("DR01 PIXHAWK STATUS")
                print("====================")
                print()

                print("Connection : OK")
                print(f"Armed      : {'YES' if status['armed'] else 'NO'}")
                print(f"Mode       : {status['mode']}")

                print()
                print("BATTERY")
                print(
                    f"Voltage    : "
                    f"{format_value(status['voltage'], '.2f')} V"
                )
                print(
                    f"Current    : "
                    f"{format_value(status['current'], '.2f')} A"
                )
                print(
                    f"Remaining  : "
                    f"{format_value(status['battery_remaining'])} %"
                )

                print()
                print("GPS")
                print(
                    f"Fix        : "
                    f"{gps_fix_name(status['gps_fix'])}"
                )
                print(
                    f"Satellites : "
                    f"{format_value(status['satellites'])}"
                )
                print(
                    f"Latitude   : "
                    f"{format_value(status['lat'], '.7f')}"
                )
                print(
                    f"Longitude  : "
                    f"{format_value(status['lon'], '.7f')}"
                )

                print()
                print("ATTITUDE")
                print(
                    f"Roll       : "
                    f"{format_value(status['roll'], '.1f')} deg"
                )
                print(
                    f"Pitch      : "
                    f"{format_value(status['pitch'], '.1f')} deg"
                )
                print(
                    f"Yaw        : "
                    f"{format_value(status['yaw'], '.1f')} deg"
                )

                last_print = now

            # ป้องกัน loop ใช้ CPU 100%
            time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nDR01 status stopped")
            break

        except Exception as e:
            print(f"\nERROR: {e}")
            time.sleep(1)


def format_value(value, fmt=None):

    if value is None:
        return "-"

    if fmt:
        return format(value, fmt)

    return str(value)


def gps_fix_name(fix):

    gps_types = {
        0: "NO GPS",
        1: "NO FIX",
        2: "2D FIX",
        3: "3D FIX",
        4: "DGPS",
        5: "RTK FLOAT",
        6: "RTK FIXED",
    }

    if fix is None:
        return "-"

    return gps_types.get(fix, f"UNKNOWN ({fix})")

def request_message_interval(master, message_id, frequency_hz):
    interval_us = int(1_000_000 / frequency_hz)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        message_id,
        interval_us,
        0,
        0,
        0,
        0,
        0
    )
if __name__ == "__main__":
    main()