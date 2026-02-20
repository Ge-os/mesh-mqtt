# Meshtastic MQTT Time-Bot – Setup Guide

Complete instructions for deploying your own Mosquitto broker and a Python
time-reply service, then configuring Meshtastic devices and the Android app to
connect to it.

---

## How It Works

```
Mesh node  ──[LoRa]──►  Gateway node  ──[WiFi/4G]──►  Mosquitto (your server)
                                                              │
           ◄─[LoRa]──   Gateway node  ◄─[WiFi/4G]──   time-service.py
```

1. Any mesh node sends a text message containing **`!time`** on the primary
   channel.
2. The gateway node relays it to your Mosquitto broker over the internet (or
   local network).
3. `mqtt_time_service.py` receives the JSON message, builds a direct reply
   with the current time, and publishes it to the **downlink** topic.
4. The gateway's `mqtt` channel picks up the downlink message and re-broadcasts
   it on the mesh as a direct message back to the requester.

> **No internet required for mesh-internal communication.** As long as one
> gateway node can reach `YOUR_SERVER_IP:1883` the entire mesh benefits.

---

## 1. Server Prerequisites

| Requirement | Minimum version |
|---|---|
| Docker + Docker Compose | Docker 24, Compose v2 |
| Open TCP port | **1883** (or 8883 for TLS) |

Make sure port **1883** is allowed in your firewall / cloud security group:

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 1883/tcp

# firewalld (Fedora/RHEL)
sudo firewall-cmd --permanent --add-port=1883/tcp
sudo firewall-cmd --reload
```

---

## 2. Clone / Place the Project

If you received this as a ZIP, extract it.  Then enter the directory:

```bash
cd mesh-mqtt
```

---

## 3. Create the `.env` File

```bash
cp .env.example .env
nano .env          # or your preferred editor
```

Set these fields:

| Variable | Description | Example |
|---|---|---|
| `SERVER_PUBLIC_IP` | Your server's public IP or domain | `203.0.113.10` |
| `MQTT_HOST` | Broker host (keep `mosquitto` inside Docker) | `mosquitto` |
| `MQTT_PORT` | Broker port | `1883` |
| `MQTT_USERNAME` | MQTT credentials | `meshuser` |
| `MQTT_PASSWORD` | Strong password | `S3cr3tPass!` |
| `TIMEZONE` | IANA timezone for the time reply | `Europe/Berlin` |
| `TIME_TRIGGER` | Trigger phrase (case-insensitive) | `!time` |

---

## 4. Create the Mosquitto Password File

Mosquitto requires a hashed password file.  Create it **before** starting the
stack (Docker image provides `mosquitto_passwd`):

```bash
docker run --rm -it \
  -v "$(pwd)/mosquitto:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/passwd meshuser
```

You will be prompted for the password.  Use the **same password** you put in
`.env` → `MQTT_PASSWORD`.

To add extra users later (e.g. for additional gateway nodes with individual
credentials):

```bash
docker run --rm -it \
  -v "$(pwd)/mosquitto:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd /mosquitto/config/passwd anotheruser
```

---

## 5. Start the Stack

```bash
docker compose up -d
```

Check that both containers are running:

```bash
docker compose ps
docker compose logs -f
```

You should see:

```
[INFO] Connected to broker mosquitto:1883
[INFO] Subscribed to msh/+/2/json/#
```

### Test the broker manually

From your server (or any machine that can reach it):

```bash
# Subscribe to all JSON mesh traffic
mosquitto_sub -h YOUR_SERVER_IP -p 1883 \
  -u meshuser -P 'S3cr3tPass!' \
  -t 'msh/#' -v

# Publish a fake time request to verify the service replies
mosquitto_pub -h YOUR_SERVER_IP -p 1883 \
  -u meshuser -P 'S3cr3tPass!' \
  -t 'msh/EU_868/2/json/LongFast/!aabbccdd' \
  -m '{"from":2864434397,"to":-1,"type":"text","payload":"!time","sender":"!aabbccdd","channel":0}'
```

The subscriber window should show a reply published to
`msh/EU_868/2/json/mqtt/`.

---

## 6. Meshtastic Device Configuration

Every Meshtastic node that should be able to query the time needs:

1. A **gateway** role (WiFi or ethernet connectivity to reach your server)  
   *— or —*  
   Any node within LoRa range of a gateway will automatically benefit.

### 6.1 Create an `mqtt` Channel (for receiving replies)

Meshtastic uses a channel literally named **`mqtt`** as the downlink entry
point.  You must create this channel with **Downlink enabled**.

#### Android App

1. Open **Meshtastic** → **Settings** → **Channels**
2. Tap the **+** button to add a new channel
3. Set:
   - **Name**: `mqtt`  *(exact, case-sensitive)*
   - **Role**: `Secondary`
   - **PSK**: generate a random key (it is not used for security here)
   - **Downlink enabled**: ✅ ON
   - **Uplink enabled**: ❌ OFF  *(replies come in, no need to uplink this channel)*
4. Tap **Save**, then **Send**

#### CLI

```bash
# Add the "mqtt" channel at the next free index (e.g. index 1)
meshtastic --ch-add mqtt
meshtastic --ch-index 1 --ch-set downlink_enabled true
meshtastic --ch-index 1 --ch-set uplink_enabled false
```

### 6.2 Enable Uplink on the Primary Channel

Nodes need to uplink text messages so the service sees them.

#### Android App

1. **Settings** → **Channels** → **LongFast** (your primary channel)
2. Enable **Uplink enabled** → **Save** → **Send**

#### CLI

```bash
meshtastic --ch-index 0 --ch-set uplink_enabled true
```

---

## 7. Android App – MQTT Module Settings

Configure the gateway node to connect to **your** broker instead of the public
one.

1. Open **Meshtastic** → **Settings** → **MQTT**
2. Fill in the following fields:

| Field | Value |
|---|---|
| **MQTT enabled** | ✅ ON |
| **Server address** | `YOUR_SERVER_IP` |
| **Username** | `meshuser` *(matches `.env`)* |
| **Password** | `S3cr3tPass!` *(matches `.env`)* |
| **Encryption enabled** | ❌ OFF – required for JSON mode |
| **JSON enabled** | ✅ ON – the service reads JSON messages |
| **TLS enabled** | ❌ OFF *(enable only if you set up TLS on port 8883)* |
| **Root topic** | *(leave blank to use default `msh/REGION`)* |
| **MQTT Client Proxy** | ✅ ON if relying on phone internet; ❌ OFF if node has WiFi |

3. Tap **Send**

### 7.1 Configure WiFi on the Gateway Node (if not using Client Proxy)

If you are **not** using Client Proxy, the node itself must connect to WiFi:

1. **Settings** → **Network**
2. Enable **WiFi enabled**, enter **SSID** and **PSK**
3. Tap **Send** — the node reboots and connects

#### CLI equivalent

```bash
meshtastic --set network.wifi_enabled true \
           --set network.wifi_ssid "YourSSID" \
           --set network.wifi_psk "YourWiFiPassword"

meshtastic --set mqtt.enabled true \
           --set mqtt.address "YOUR_SERVER_IP" \
           --set mqtt.username "meshuser" \
           --set mqtt.password "S3cr3tPass!" \
           --set mqtt.json_enabled true \
           --set mqtt.encryption_enabled false
```

---

## 8. Usage

From **any** node in the mesh, send a text message:

```
!time
```

Within a few seconds you will receive a direct reply such as:

```
Current time: 2026-02-20 14:35:07 CET
```

The trigger is **case-insensitive** and can be embedded in a longer message
(`"hey, !time please"` also works).  Change `TIME_TRIGGER` in `.env` to any
phrase you prefer, then restart the service:

```bash
docker compose up -d --force-recreate time-service
```

---

## 9. Optional: TLS (Encrypted Connections)

1. Obtain a certificate (e.g. Let's Encrypt via `certbot`):
   ```bash
   sudo certbot certonly --standalone -d yourdomain.example
   ```
2. Copy/symlink the certs into `./mosquitto/certs/`
3. Uncomment the `listener 8883` block in `mosquitto/mosquitto.conf`
4. In the Android MQTT settings, change the **Server address** to
   `ssl://yourdomain.example` and enable **TLS enabled**
5. Open port **8883** in your firewall
6. Restart: `docker compose restart mosquitto`

---

## 10. Updating

```bash
docker compose pull           # pull latest Mosquitto image
docker compose up -d --build  # rebuild the Python service image
```

---

## 11. Troubleshooting

| Symptom | Check |
|---|---|
| No connection from node | Firewall allows TCP 1883; `SERVER_PUBLIC_IP` is correct |
| "Connection refused" in logs | Broker not started; run `docker compose ps` |
| No reply to `!time` | JSON not enabled on MQTT module; Encryption not disabled |
| Reply never arrives on mesh | `mqtt` channel missing or Downlink not enabled on gateway node |
| Time zone wrong | `TIMEZONE` in `.env` uses wrong IANA name; verify with `pytz.all_timezones` |

View live service logs at any time:

```bash
docker compose logs -f time-service
```
