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

- LVGL library
- ATD1.47-S3 library
- ESPAsyncWebServer
- ArduinoJson

## Setup

1. Install the required libraries in Arduino IDE
2. Configure WiFi credentials in the code
3. Upload the sketch to your ESP32-S3
4. Access the web interface using the IP address shown on the display

## Usage

The system can be controlled through:
- Physical buttons on the device
- Web interface (access via device IP address)

## API Endpoints

- GET /api/status - Get current status of all valves
- POST /api/valve - Control valve state (parameters: valve, action) 