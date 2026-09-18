import os
import ssl
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

HOST = os.getenv("MQTT_HOST")
PORT = int(os.getenv("MQTT_PORT", "8883"))
USER = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")

print("Host:", HOST)
print("Port:", PORT)
print("User:", USER)
print("Password loaded:", bool(PASSWORD))


def on_connect(client, userdata, flags, reason_code, properties):
    print("CONNECT RESULT:", reason_code)

    if reason_code == 0:
        print("✅ MQTT connection successful!")
        client.subscribe("home/demo/state")
        print("📡 Subscribed to home/demo/state")
    else:
        print("❌ MQTT connection failed")


def on_message(client, userdata, msg):
    print("📥 Received message:")
    print(msg.topic)
    print(msg.payload.decode())


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="sharp-mqtt-test"
)

client.username_pw_set(USER, PASSWORD)

client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

client.on_connect = on_connect
client.on_message = on_message

print("🔌 Connecting to HiveMQ...")

client.connect(HOST, PORT, keepalive=60)

client.loop_forever()