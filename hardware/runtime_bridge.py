"""
SHARP live runtime bridge.

Purpose
-------
The RL/model input stream (home/<house>/state) is not the same thing as
hardware-confirmed runtime telemetry. This bridge keeps those concerns separate:

    state (model input / replay / state builder)
        + actuator ACKs from the Raspberry Pi
        + live weather already sent over MQTT
        -> runtime (retained, dashboard-facing truth)

The dashboard should subscribe to home/<house>/runtime, never manufacture a
HomeState from mock data.

Important
---------
There is no PZEM in the current prototype. Appliance power is therefore an
estimate derived from GPIO-confirmed ON/OFF state multiplied by the catalogued
15-minute mean wattage. measured_w stays null.
"""

from __future__ import annotations

import copy
import json
import os
import ssl
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
HOUSE_ID = os.getenv("HOUSE_ID", "demo")

STATE_TOPIC = f"home/{HOUSE_ID}/state"
RUNTIME_TOPIC = f"home/{HOUSE_ID}/runtime"
INTENT_TOPIC = f"home/{HOUSE_ID}/intent"
ACK_SUB = f"home/{HOUSE_ID}/actuator/+/ack"
PI_HEALTH_TOPIC = f"home/{HOUSE_ID}/health/pi"
BRIDGE_HEALTH_TOPIC = f"home/{HOUSE_ID}/health/runtime"
WEATHER_TOPIC = f"home/{HOUSE_ID}/weather"
GRID_EVENT_TOPIC = f"home/{HOUSE_ID}/grid/event"

IST = ZoneInfo("Asia/Kolkata")

# This is the physically wired prototype currently represented by pi_agent.py.
# Watts are model/catalogue estimates, not meter measurements.
WIRED_DEVICES = {
    "air_conditioner_01": {
        "display_name": "Air Conditioner",
        "appliance_type": "air_conditioner",
        "service_class": "thermostatic",
        "is_necessity": False,
        "rated_w": 1328.4,
    },
    "refrigerator_01": {
        "display_name": "Refrigerator",
        "appliance_type": "refrigerator",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 43.2,
    },
    "washing_machine_01": {
        "display_name": "Washing Machine",
        "appliance_type": "washing_machine",
        "service_class": "deferrable",
        "is_necessity": False,
        "rated_w": 113.7,
    },
    "mixer_grinder_01": {
        "display_name": "Mixer Grinder",
        "appliance_type": "mixer_grinder",
        "service_class": "interruptible",
        "is_necessity": False,
        "rated_w": 500.0,
    },
    "television_01": {
        "display_name": "Television",
        "appliance_type": "television",
        "service_class": "interruptible",
        "is_necessity": False,
        "rated_w": 104.6,
    },
    "ev_charger_01": {
        "display_name": "EV Charger (prototype)",
        "appliance_type": "ev_charger",
        "service_class": "deferrable",
        "is_necessity": False,
        "rated_w": float(os.getenv("EV_CHARGER_PROXY_W", "1500")),
    },
}

latest_input_state: dict | None = None
latest_weather: dict | None = None
latest_pi_health: dict | None = None
latest_grid_event: dict | None = None
last_state_received_mono = 0.0

# Hardware-confirmed state from actuator ACK messages.
confirmed = {
    appliance_id: {
        "level": 0,
        "gpio_state": 0,
        "acked": False,
        "acked_at": None,
    }
    for appliance_id in WIRED_DEVICES
}


def now_ist() -> str:
    return datetime.now(IST).isoformat()


def json_payload(msg) -> dict | None:
    try:
        value = json.loads(msg.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def source_appliances() -> dict[str, dict]:
    if not latest_input_state:
        return {}

    apps = latest_input_state.get("appliances", [])
    if not isinstance(apps, list):
        return {}

    return {
        item.get("appliance_id"): item
        for item in apps
        if isinstance(item, dict) and item.get("appliance_id")
    }


def build_runtime_state() -> dict | None:
    """
    Merge model-input context with actual Raspberry Pi ACK/readback state.

    The model input remains useful for fields we cannot physically measure in
    this prototype (tariff, occupancy context, thermal-model estimate, etc.).
    Every such field is explicitly marked as model/config-derived. Appliance
    ON/OFF and gpio_state come from real ACKs whenever available.
    """
    if latest_input_state is None:
        return None

    src = latest_input_state
    src_apps = source_appliances()
    appliances = []
    controllable_w = 0.0

    for appliance_id, meta in WIRED_DEVICES.items():
        source = src_apps.get(appliance_id, {})
        hw = confirmed[appliance_id]

        # Before the first ACK, do not claim actuation verification. We may show
        # the incoming intended level, but it is clearly unverified.
        if hw["acked"]:
            level = int(hw["level"])
            gpio_state = int(hw["gpio_state"])
            verified = True
        else:
            level = int(source.get("level", 0) or 0)
            gpio_state = int(source.get("gpio_state", 1 if level else 0) or 0)
            verified = False

        power_w = meta["rated_w"] if level != 0 else 0.0
        controllable_w += power_w

        appliances.append(
            {
                "appliance_id": appliance_id,
                "display_name": meta["display_name"],
                "appliance_type": meta["appliance_type"],
                "service_class": meta["service_class"],
                "is_necessity": meta["is_necessity"],
                "supports_reduced": False,
                "slot": source.get("slot"),
                "level": level,
                "occupant_wants": bool(source.get("occupant_wants", False)),
                "peak_locked_out": bool(source.get("peak_locked_out", False)),
                "power_15min_mean_w": round(power_w, 3),
                "measured_w": None,
                "gpio_state": gpio_state,
                "actuation_verified": verified,
                "remaining_service_hours": float(
                    source.get("remaining_service_hours", 0.0) or 0.0
                ),
                "shed_reason": source.get("shed_reason"),
                "deferred_until": source.get("deferred_until"),
                "power_basis": "gpio_state_x_catalogued_15min_mean_w",
                "last_hardware_ack": hw["acked_at"],
            }
        )

    background_kw = float(src.get("background_load_kw", 0.0) or 0.0)
    aggregate_kw = background_kw + controllable_w / 1000.0

    runtime = copy.deepcopy(src)
    runtime.update(
        {
            "schema_version": "sharp_runtime_v1",
            "source": "sharp_runtime_bridge",
            "house_id": HOUSE_ID,
            "timestamp_ist": now_ist(),
            "aggregate_power_kw": round(aggregate_kw, 4),
            "appliances": appliances,
            "data_age_seconds": round(
                max(0.0, time.monotonic() - last_state_received_mono), 1
            ),
            "power_basis": "estimated_from_gpio_and_catalogue",
            "measured_power_available": False,
            "runtime_truth": {
                "gpio_state": "hardware_ack_readback",
                "appliance_level": "hardware_ack_when_available",
                "appliance_power": "estimated_not_measured",
                "measured_w": "unavailable_no_meter",
                "context_fields": "model_input_or_config_derived",
            },
        }
    )

    if latest_grid_event:
        action = latest_grid_event.get("action")
        if action == "declare":
            try:
                severity = float(latest_grid_event.get("severity", 0.0))
                if 0.0 <= severity <= 1.0:
                    runtime["grid_peak_severity"] = severity
                    runtime["grid_event"] = latest_grid_event
            except (TypeError, ValueError):
                pass
        elif action == "cancel":
            runtime["grid_peak_severity"] = 0.0
            runtime["grid_event"] = latest_grid_event

    if latest_weather:
        weather = latest_weather.get("weather", latest_weather)
        if isinstance(weather, dict):
            runtime["weather"] = weather
            outdoor = weather.get("outdoor_temperature_c")
            if isinstance(outdoor, (int, float)):
                runtime["outdoor_temperature_c"] = float(outdoor)

    return runtime


def publish_runtime(client: mqtt.Client) -> None:
    state = build_runtime_state()
    if state is None:
        return

    client.publish(
        RUNTIME_TOPIC,
        json.dumps(state),
        qos=0,
        retain=True,
    )


def publish_bridge_health(client: mqtt.Client, status: str = "online") -> None:
    payload = {
        "source": "sharp_runtime_bridge",
        "status": status,
        "house_id": HOUSE_ID,
        "timestamp_ist": now_ist(),
        "input_state_available": latest_input_state is not None,
        "pi_status": (latest_pi_health or {}).get("status", "unknown"),
        "hardware_confirmed_devices": sum(
            1 for item in confirmed.values() if item["acked"]
        ),
        "wired_devices": len(WIRED_DEVICES),
        "measured_power_available": False,
    }

    client.publish(
        BRIDGE_HEALTH_TOPIC,
        json.dumps(payload),
        qos=0,
        retain=True,
    )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"MQTT connection failed: {reason_code}")
        return

    print(f"Connected to HiveMQ as runtime bridge for house={HOUSE_ID}")

    client.subscribe(
        [
            (STATE_TOPIC, 0),
            (ACK_SUB, 1),
            (PI_HEALTH_TOPIC, 0),
            (WEATHER_TOPIC, 0),
            (GRID_EVENT_TOPIC, 1),
        ]
    )

    publish_bridge_health(client)


def on_message(client, userdata, msg):
    global latest_input_state
    global latest_weather
    global latest_pi_health
    global latest_grid_event
    global last_state_received_mono

    payload = json_payload(msg)
    if payload is None:
        print(f"Ignoring non-JSON payload on {msg.topic}")
        return

    if msg.topic == STATE_TOPIC:
        # This is the validated/model input stream. The bridge never publishes
        # back to this topic, so there is no state -> state feedback loop.
        latest_input_state = payload
        last_state_received_mono = time.monotonic()
        publish_runtime(client)
        publish_bridge_health(client)
        return

    if msg.topic == PI_HEALTH_TOPIC:
        latest_pi_health = payload
        publish_bridge_health(client)
        return

    if msg.topic == WEATHER_TOPIC:
        latest_weather = payload
        publish_runtime(client)
        return

    if msg.topic == GRID_EVENT_TOPIC:
        latest_grid_event = payload
        publish_runtime(client)
        return

    if "/actuator/" in msg.topic and msg.topic.endswith("/ack"):
        appliance_id = payload.get("appliance_id")

        if appliance_id not in confirmed:
            return

        # Only accepted ACKs prove that the commanded hardware state was applied.
        if payload.get("accepted") is True:
            confirmed[appliance_id]["level"] = int(
                payload.get("applied_level", 0) or 0
            )
            confirmed[appliance_id]["gpio_state"] = int(
                payload.get("gpio_state", 0) or 0
            )
            confirmed[appliance_id]["acked"] = True
            confirmed[appliance_id]["acked_at"] = payload.get(
                "acked_at", now_ist()
            )

        publish_runtime(client)
        publish_bridge_health(client)


def main():
    missing = [
        name
        for name, value in (
            ("MQTT_HOST", MQTT_HOST),
            ("MQTT_USER", MQTT_USER),
            ("MQTT_PASS", MQTT_PASS),
        )
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
        )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sharp-runtime-bridge-{HOUSE_ID}",
    )

    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.will_set(
        BRIDGE_HEALTH_TOPIC,
        json.dumps(
            {
                "source": "sharp_runtime_bridge",
                "status": "offline",
                "house_id": HOUSE_ID,
            }
        ),
        qos=0,
        retain=True,
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("=" * 68)
    print("SHARP LIVE RUNTIME BRIDGE")
    print("=" * 68)
    print(f"Input state : {STATE_TOPIC}")
    print(f"Runtime     : {RUNTIME_TOPIC}")
    print(f"GPIO ACKs   : {ACK_SUB}")
    print(f"Weather     : {WEATHER_TOPIC}")
    print(f"Grid event  : {GRID_EVENT_TOPIC}")
    print("Power       : GPIO-confirmed estimate; measured_w remains null")
    print("=" * 68)

    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            publish_runtime(client)
            publish_bridge_health(client)
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            publish_bridge_health(client, status="offline")
            time.sleep(0.2)
        finally:
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()
