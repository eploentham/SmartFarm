# Smart Farm Timer Controller

This project implements a timer-based irrigation control system using an ESP32-S3 microcontroller with a 1.47" display. It controls 8 water valves and provides both physical button and web interface control.

## Features

- Control 8 water valves independently
- Physical button control interface
- Web-based control interface
- Real-time status display
- WiFi connectivity
- NTP time synchronization
- Visual feedback through display

## Hardware Requirements

- ESP32-S3 microcontroller
- 1.47" display
- 8 water valves
- WiFi network

## Pin Configuration

- Valve 1: GPIO 15
- Valve 2: GPIO 16
- Valve 3: GPIO 17
- Valve 4: GPIO 18
- Valve 5: GPIO 42
- Valve 6: GPIO 41
- Valve 7: GPIO 40
- Valve 8: GPIO 39

## Dependencies

Required libraries (install via Arduino Library Manager or GitHub):

1. LVGL (https://github.com/lvgl/lvgl)
2. ATD1.47-S3 (from Arduino Library Manager)
3. ESPAsyncWebServer (https://github.com/me-no-dev/ESPAsyncWebServer)
4. AsyncTCP (https://github.com/me-no-dev/AsyncTCP) - Required for ESPAsyncWebServer
5. ArduinoJson (https://github.com/bblanchon/ArduinoJson)

## Setup

1. Install the required libraries in Arduino IDE:
   - Open Arduino IDE
   - Go to Tools > Manage Libraries
   - Search for and install:
     - LVGL
     - ATD1.47-S3
     - ArduinoJson
   - Install ESPAsyncWebServer and AsyncTCP from GitHub:
     - Download the libraries from their respective GitHub repositories
     - Extract them to your Arduino libraries folder (usually Documents/Arduino/libraries)

2. Configure WiFi credentials in the code:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```

3. Upload the sketch to your ESP32-S3
4. Access the web interface using the IP address shown on the display

## Usage

The system can be controlled through:
- Physical buttons on the device
- Web interface (access via device IP address)

## API Endpoints

- GET /api/status - Get current status of all valves
- POST /api/valve - Control valve state (parameters: valve, action) 