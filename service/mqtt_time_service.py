#!/usr/bin/env python3
"""
Meshtastic MQTT Time Service
----------------------------
Subscribes to all JSON uplink topics on the local Mosquitto broker.
When any node sends a text message whose payload contains the configured
trigger word (default: "!time"), the service replies with the current
time via the JSON downlink topic so the gateway node relays it back onto
the mesh.

Message flow
  Mesh node  →  [LoRa]  →  Gateway node  →  [WiFi/4G]  →  Mosquitto
                          ←  [WiFi/4G]  ←               ←  this service

Relevant Meshtastic MQTT topics (JSON mode):
  Uplink  : msh/<REGION>/2/json/<CHANNEL>/!<gateway_node_id>
  Downlink: msh/<REGION>/2/json/mqtt/
"""

import json
import logging
import os
from datetime import datetime

import paho.mqtt.client as mqtt
import pytz
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration (from .env)
# ---------------------------------------------------------------------------
MQTT_HOST     = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
TIMEZONE      = os.getenv("TIMEZONE", "UTC")
TIME_TRIGGER  = os.getenv("TIME_TRIGGER", "!time").lower()
BOT_NODE_ID   = os.getenv("BOT_NODE_ID", "")   # hex, e.g. !aabbccdd  (optional override)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def current_time_str() -> str:
    """Return a human-readable local time string."""
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


def hex_node_id_to_decimal(hex_id: str) -> int:
    """Convert '!aabbccdd' → 2864434397."""
    return int(hex_id.lstrip("!"), 16)


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        log.info("Connected to broker %s:%s", MQTT_HOST, MQTT_PORT)
        # Subscribe to all JSON uplink topics, all regions and channels.
        # msh/+/2/json/# catches e.g. msh/EU_868/2/json/LongFast/!aabbccdd
        client.subscribe("msh/+/2/json/#")
        log.info("Subscribed to msh/+/2/json/#")
    else:
        log.error("Connection refused, reason code %s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("Disconnected (code %s). Will auto-reconnect.", reason_code)


def on_message(client, userdata, message):
    topic = message.topic

    # -----------------------------------------------------------------------
    # Parse topic: msh/<REGION>/2/json/<CHANNEL>/!<gateway_id>
    #   parts[0] = "msh"
    #   parts[1] = region  (e.g. "EU_868", "US")
    #   parts[2] = "2"
    #   parts[3] = "json"
    #   parts[4] = channel name
    #   parts[5] = gateway node hex id (e.g. "!aabbccdd")
    # -----------------------------------------------------------------------
    parts = topic.split("/")
    if len(parts) < 6:
        return

    region      = parts[1]
    channel     = parts[4]
    gateway_hex = parts[5]   # e.g. "!aabbccdd"

    # Skip our own downlink channel (avoid echo loops)
    if channel == "mqtt":
        return

    # -----------------------------------------------------------------------
    # Decode JSON payload
    # -----------------------------------------------------------------------
    try:
        data = json.loads(message.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.debug("Cannot parse payload on %s: %s", topic, exc)
        return

    msg_type = data.get("type", "")
    payload  = data.get("payload", "")

    # Only care about plain text messages
    if msg_type != "text" or not isinstance(payload, str):
        return

    # Check trigger word
    if TIME_TRIGGER not in payload.lower():
        return

    sender_decimal = data.get("from")   # decimal node ID of the sender
    if sender_decimal is None:
        log.warning("Received time request but 'from' field is missing: %s", data)
        return

    log.info(
        "Time request from node %s via gateway %s on channel '%s' (%s)",
        hex(sender_decimal), gateway_hex, channel, region,
    )

    # -----------------------------------------------------------------------
    # Build the response
    #
    # For Meshtastic JSON downlink the "from" field must be the decimal node
    # ID of the gateway that will transmit the reply.  We take it from the
    # topic rather than relying on BOT_NODE_ID so the correct gateway is
    # always used even in multi-gateway setups.
    # -----------------------------------------------------------------------
    if not gateway_hex.startswith("!"):
        log.warning("Unexpected gateway id format: %s", gateway_hex)
        return

    try:
        gateway_decimal = hex_node_id_to_decimal(gateway_hex)
    except ValueError:
        log.error("Cannot convert gateway id '%s' to decimal", gateway_hex)
        return

    time_str = current_time_str()
    response = {
        "from":    gateway_decimal,
        "type":    "sendtext",
        "payload": f"Current time: {time_str}",
        "to":      sender_decimal,   # direct reply (not broadcast)
    }

    # Downlink topic for this region so the gateway relays it back to the mesh
    downlink_topic = f"msh/{region}/2/json/mqtt/"
    payload_json   = json.dumps(response)

    client.publish(downlink_topic, payload_json, qos=0)
    log.info("Published time reply to %s: %s", downlink_topic, payload_json)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("Starting Meshtastic MQTT Time Service")
    log.info("  Broker   : %s:%s", MQTT_HOST, MQTT_PORT)
    log.info("  Timezone : %s", TIMEZONE)
    log.info("  Trigger  : %s", TIME_TRIGGER)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mesh-time-service")
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    # Blocking event loop with automatic reconnect
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
