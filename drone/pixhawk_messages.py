from pymavlink import mavutil

PORT = "/dev/ttyACM0"

print("Connecting Pixhawk...")

master = mavutil.mavlink_connection(PORT)

print("Waiting for HEARTBEAT...")
master.wait_heartbeat()

print("Connected")
print("Receiving MAVLink messages...")
print("Press Ctrl+C to stop\n")

try:
    while True:
        msg = master.recv_match(
            blocking=True,
            timeout=5
        )

        if msg is None:
            print("No message")
            continue

        print(msg.get_type())

except KeyboardInterrupt:
    print("\nStopped")