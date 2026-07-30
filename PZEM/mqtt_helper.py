"""
mqtt_helper.py — thin wrapper around paho-mqtt for the pump-energy pipeline.

Handles connect/subscribe/reconnect and hands each decoded message to a
user-supplied callback: on_reading(topic, payload_dict).
"""

import json
import logging

import paho.mqtt.client as mqtt

import config

log = logging.getLogger("mqtt_helper")


class MqttSubscriber:
    def __init__(self, on_reading, topic=None):
        """on_reading(topic:str, payload:dict) is called per valid JSON message.

        topic: MQTT topic filter to subscribe to. Defaults to config.MQTT_TOPIC
        (the pump-energy tree); pass MQTT_PRESSURE_TOPIC for the pressure logger.
        """
        self._on_reading = on_reading
        self._topic = topic or config.MQTT_TOPIC
        self._client = mqtt.Client()
        if config.MQTT_USER:
            self._client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Connected to MQTT %s:%d", config.MQTT_BROKER, config.MQTT_PORT)
            client.subscribe(self._topic)
            log.info("Subscribed to %s", self._topic)
        else:
            log.error("MQTT connect failed rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error("Bad payload on %s: %s", msg.topic, e)
            return
        self._on_reading(msg.topic, payload)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            log.warning("Unexpected MQTT disconnect rc=%s (auto-reconnect)", rc)

    def connect(self):
        self._client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)

    def loop_start(self):
        self._client.loop_start()

    def loop_stop(self):
        self._client.loop_stop()
        self._client.disconnect()
