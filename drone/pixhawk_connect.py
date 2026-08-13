from pymavlink import mavutil
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

    return master


def main():

    while True:
        try:
            master = connect_pixhawk()

            # Connected successfully.
            # Keep checking HEARTBEAT.
            while True:

                heartbeat = master.recv_match(
                    type="HEARTBEAT",
                    blocking=True,
                    timeout=3
                )

                if heartbeat is None:
                    raise TimeoutError("HEARTBEAT lost")

                print("HEARTBEAT OK")

        except KeyboardInterrupt:
            print("\nDR01 stopped")
            break

        except Exception as e:
            print(f"ERROR: {e}")
            print("Reconnect in 3 seconds...")
            time.sleep(3)


if __name__ == "__main__":
    main()