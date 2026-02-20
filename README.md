# mesh-mqtt – Meshtastic MQTT Time Bot

A self-hosted MQTT broker + Python bot that replies with the current time when
any Meshtastic mesh node sends `!time`.

## Project Structure

```
mesh-mqtt/
├── .env.example               ← copy to .env and fill in your values
├── docker-compose.yml         ← Mosquitto + time-service in one command
├── mosquitto/
│   └── mosquitto.conf         ← Mosquitto broker configuration
├── service/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── mqtt_time_service.py   ← Python time-reply service
└── docs/
    └── setup-guide.md         ← Full setup & Android app configuration guide
```

## Quick Start

```bash
cp .env.example .env
# edit .env – set SERVER_PUBLIC_IP, MQTT_PASSWORD, TIMEZONE

# Create Mosquitto password file
docker run --rm -it \
  -v "$(pwd)/mosquitto:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/passwd meshuser

# Start everything
docker compose up -d
```

See **[docs/setup-guide.md](docs/setup-guide.md)** for full instructions
including Android app configuration and Meshtastic channel setup.

## How to Use

Send `!time` in any text message from a mesh node → receive the current time
as a direct reply within seconds.

Trigger word and timezone are configurable in `.env`.
