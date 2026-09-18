import os
import json
import ssl
import time
from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

HOUSE_ID = "demo"


# ============================================================
# PI MQTT TOPICS
# ============================================================

# Pi receives commands from the RL/controller layer.
ACTUATOR_CMD_SUB = f"home/{HOUSE_ID}/actuator/+/cmd"

# Pi receives resident override requests.
OVERRIDE_SUB = f"home/{HOUSE_ID}/override/+"

# Pi publishes execution acknowledgements.
ACTUATOR_ACK_PREFIX = f"home/{HOUSE_ID}/actuator"


# ============================================================
# HARDWARE REGISTRY
# ============================================================

# BCM GPIO numbers from the prototype specification.
# GPIO is NOT actually driven yet.

DEVICES = {
    "ceiling_fan": {
        "gpio": 17,
        "necessity": True,
        "supports_reduced": True,
    },
    "table_fan": {
        "gpio": 27,
        "necessity": True,
        "supports_reduced": True,
    },
    "light1": {
        "gpio": 22,
        "necessity": True,
        "supports_reduced": True,
    },
    "light2": {
        "gpio": 19,
        "necessity": True,
        "supports_reduced": True,
    },
    "refrigerator": {
        "gpio": 23,
        "necessity": True,
        "supports_reduced": False,
    },
    "air_conditioner": {
        "gpio": 16,
        "necessity": False,
        "supports_reduced": False,
    },
    "washing_machine": {
        "gpio": 20,
        "necessity": False,
        "supports_reduced": False,
    },
    "ev_charger": {
        "gpio": 6,
        "necessity": False,
        "supports_reduced": False,
    },
    "tv": {
        "gpio": 21,
        "necessity": False,
        "supports_reduced": False,
    },
    "mixer_grinder": {
        "gpio": 26,
        "necessity": False,
        "supports_reduced": False,
    },
}


# ============================================================
# CURRENT HARDWARE STATE
# ============================================================

current_levels = {
    device_id: 1
    for device_id in DEVICES
}


# ============================================================
# UTILITY
# ============================================================

def timestamp_ist():
    """
    Temporary timestamp helper.

    The actual Pi implementation can use the system's
    synchronized local clock.
    """
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# SAFETY VALIDATION
# ============================================================

def validate_command(appliance_id, level):
    """
    Basic Stage-1 safety validation.

    Full compressor/cycle/min-on/min-off/watchdog logic
    will be added when we integrate the actual hardware layer.
    """

    if appliance_id not in DEVICES:
        return False, "GPIO_FAILURE"

    device = DEVICES[appliance_id]

    # Level must be 0, 1, or 2.
    if level not in (0, 1, 2):
        return False, "LEVEL_UNSUPPORTED"

    # Necessity appliances cannot be turned OFF.
    if device["necessity"] and level == 0:
        return False, "NECESSITY_MASK"

    # Reduced level only if supported.
    if level == 2 and not device["supports_reduced"]:
        return False, "LEVEL_UNSUPPORTED"

    return True, None


# ============================================================
# GPIO PLACEHOLDER
# ============================================================

def apply_gpio(appliance_id, level):
    """
    SIMULATED GPIO.

    This does NOT touch real hardware.

    Tomorrow, when running on Raspberry Pi, this function
    will be replaced with actual GPIO output code.
    """

    print(
        f"🔧 [SIMULATED GPIO] "
        f"{appliance_id} -> level {level}"
    )

    current_levels[appliance_id] = level

    # Simulated GPIO state.
    gpio_state = 1 if level != 0 else 0

    return gpio_state


# ============================================================
# ACK
# ============================================================

def publish_ack(
    client,
    command_id,
    appliance_id,
    accepted,
    applied_level,
    rejected_reason,
    gpio_state,
    latency_ms,
):
    ack = {
        "schema_version": "sharp_ack_v2",
        "command_id": command_id,
        "appliance_id": appliance_id,
        "accepted": accepted,
        "applied_level": applied_level,
        "rejected_reason": rejected_reason,
        "gpio_state": gpio_state,
        "measured_w": None,
        "verification": "NO_METER",
        "acked_at": timestamp_ist(),
        "latency_ms": latency_ms,
    }

    topic = (
        f"{ACTUATOR_ACK_PREFIX}/"
        f"{appliance_id}/ack"
    )

    client.publish(
        topic,
        json.dumps(ack),
        qos=1,
    )

    print(f"📤 ACK → {topic}")
    print(json.dumps(ack, indent=2))


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(client, payload):
    start = time.perf_counter()

    try:
        command = json.loads(payload)
    except json.JSONDecodeError:
        print("❌ Invalid JSON command")
        return

    appliance_id = command.get("appliance_id")
    command_id = command.get("command_id")
    level = command.get("level")

    print("\n📥 COMMAND")
    print(json.dumps(command, indent=2))

    valid, reason = validate_command(
        appliance_id,
        level,
    )

    if not valid:
        latency_ms = round(
            (time.perf_counter() - start) * 1000,
            2,
        )

        publish_ack(
            client=client,
            command_id=command_id,
            appliance_id=appliance_id,
            accepted=False,
            applied_level=current_levels.get(
                appliance_id,
                0,
            ),
            rejected_reason=reason,
            gpio_state=(
                1
                if current_levels.get(
                    appliance_id,
                    0,
                ) != 0
                else 0
            ),
            latency_ms=latency_ms,
        )

        print(f"🛡️ COMMAND BLOCKED: {reason}")
        return

    # Apply simulated GPIO.
    gpio_state = apply_gpio(
        appliance_id,
        level,
    )

    latency_ms = round(
        (time.perf_counter() - start) * 1000,
        2,
    )

    publish_ack(
        client=client,
        command_id=command_id,
        appliance_id=appliance_id,
        accepted=True,
        applied_level=level,
        rejected_reason=None,
        gpio_state=gpio_state,
        latency_ms=latency_ms,
    )


# ============================================================
# OVERRIDE HANDLER
# ============================================================

def handle_override(client, payload):
    try:
        override = json.loads(payload)
    except json.JSONDecodeError:
        print("❌ Invalid override JSON")
        return

    print("\n👤 RESIDENT OVERRIDE")
    print(json.dumps(override, indent=2))

    appliance_id = override.get("appliance_id")
    requested_level = override.get("requested_level")

    command = {
        "schema_version": "sharp_cmd_v2",
        "command_id": override.get(
            "override_id",
            f"override-{int(time.time())}",
        ),
        "appliance_id": appliance_id,
        "level": requested_level,
        "issued_at": timestamp_ist(),
        "expires_at": None,
    }

    handle_command(
        client,
        json.dumps(command),
    )


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    print(f"🔌 MQTT CONNECT: {reason_code}")

    if reason_code != 0:
        print("❌ MQTT connection failed")
        return

    print("✅ Connected to HiveMQ")

    # --------------------------------------------------------
    # Pi SUBSCRIBES to commands
    # --------------------------------------------------------

    client.subscribe(
        ACTUATOR_CMD_SUB,
        qos=1,
    )

    # --------------------------------------------------------
    # Pi SUBSCRIBES to resident overrides
    # --------------------------------------------------------

    client.subscribe(
        OVERRIDE_SUB,
        qos=1,
    )

    print(
        f"📡 Subscribed to "
        f"{ACTUATOR_CMD_SUB}"
    )

    print(
        f"📡 Subscribed to "
        f"{OVERRIDE_SUB}"
    )


def on_message(client, userdata, msg):
    print(f"\n📨 MQTT MESSAGE: {msg.topic}")

    payload = msg.payload.decode()

    if "/override/" in msg.topic:
        handle_override(
            client,
            payload,
        )

    elif (
        "/actuator/" in msg.topic
        and msg.topic.endswith("/cmd")
    ):
        handle_command(
            client,
            payload,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if not all([
        MQTT_HOST,
        MQTT_USER,
        MQTT_PASS,
    ]):
        raise RuntimeError(
            "Missing MQTT_HOST, MQTT_USER, or MQTT_PASS "
            "in root .env"
        )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sharp-pi-agent",
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASS,
    )

    client.tls_set(
        cert_reqs=ssl.CERT_REQUIRED,
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("🚀 Starting SHARP Pi Agent")
    print(f"Host: {MQTT_HOST}")
    print(f"Port: {MQTT_PORT}")
    print("⚠️ GPIO MODE: SIMULATED")

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=60,
    )

    client.loop_forever()


if __name__ == "__main__":
    main()