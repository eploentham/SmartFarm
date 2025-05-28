import time
import board
import adafruit_dht

# Set the pin (change to match your wiring)
dht_pin = board.D4  # GPIO4

# Initialize the DHT device (DHT22 or DHT11)
dht_device = adafruit_dht.DHT22(dht_pin)
# If using DHT11, uncomment the following line instead
# dht_device = adafruit_dht.DHT11(dht_pin)

# Main loop
while True:
    try:
        # Read temperature and humidity
        temperature = dht_device.temperature
        humidity = dht_device.humidity
        
        # Print values
        print(f"Temperature: {temperature:.1f}°C")
        print(f"Humidity: {humidity:.1f}%")
        
    except RuntimeError as e:
        # DHT sensors sometimes fail to read, just try again
        print(f"Reading error: {e}")
    except Exception as e:
        # Other errors, print the error and exit
        dht_device.exit()
        raise e
    
    # Wait before next reading
    time.sleep(2)