"""
SHARP live runtime bridge.

Purpose
-------
Keep model-input state separate from command ACKs and Pi GPIO pin readback.
The runtime topic is retained for the dashboard, but a command ACK is not proof
that an appliance operated.

    model input + command ACKs + Pi GPIO pin readback
        -> runtime with explicit verification status

Important
---------
There is no PZEM/current sensor in this prototype. GPIO readback only reports
the Pi output pin level; it cannot confirm relay contacts, appliance operation,
or actual power draw. Power is estimated from catalogue wattage only when a
real Pi GPIO readback is available. measured_w remains null.
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
GRID_WARNING_TOPIC = f"home/{HOUSE_ID}/grid/warning"

PEAK_FLEXIBLE_IDS = {
    "air_conditioner_01",
    "ev_charger_01",
    "washing_machine_01",
    "television_01",
    "mixer_grinder_01",
}

IST = ZoneInfo("Asia/Kolkata")

# Final 10-device hardware registry. Keep IDs/flags/powers aligned with pi_agent.py and mock_rl_state.py.
# Watts are catalogue/model estimates, not meter measurements.
WIRED_DEVICES = {
    "air_conditioner_01": {
        "display_name": "Air Conditioner",
        "appliance_type": "air_conditioner",
        "service_class": "thermostatic",
        "is_necessity": False,
        "rated_w": 1328.4,
    },
    "ceiling_fan_01": {
        "display_name": "Motor Fan",
        "appliance_type": "ceiling_fan",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 60.0,
    },
    "ev_charger_01": {
        "display_name": "EV Charger",
        "appliance_type": "ev_charger",
        "service_class": "deferrable",
        "is_necessity": False,
        "rated_w": 700.0,
    },
    "led_bulb_01": {
        "display_name": "Light 1",
        "appliance_type": "led_bulb",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 9.0,
    },
    "led_tube_01": {
        "display_name": "Light 2",
        "appliance_type": "led_tube",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 20.0,
    },
    "mixer_grinder_01": {
        "display_name": "Mixer Grinder",
        "appliance_type": "mixer_grinder",
        "service_class": "interruptible",
        "is_necessity": False,
        "rated_w": 500.0,
    },
    "refrigerator_01": {
        "display_name": "Refrigerator",
        "appliance_type": "refrigerator",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 43.2,
    },
    "table_fan_01": {
        "display_name": "USB Fan",
        "appliance_type": "table_fan",
        "service_class": "critical",
        "is_necessity": True,
        "rated_w": 40.0,
    },
    "television_01": {
        "display_name": "Television",
        "appliance_type": "television",
        "service_class": "interruptible",
        "is_necessity": False,
        "rated_w": 80.0,
    },
    "washing_machine_01": {
        "display_name": "Washing Machine",
        "appliance_type": "washing_machine",
        "service_class": "deferrable",
        "is_necessity": False,
        "rated_w": 113.7,
    },
}

latest_input_state: dict | None = None
latest_weather: dict | None = None
latest_pi_health: dict | None = None
latest_grid_event: dict | None = None
latest_grid_warning: dict | None = None
last_state_received_mono = 0.0

# ACK/readback state. GPIO readback confirms only the Pi pin level,
# not that the connected appliance physically operated.
confirmed = {
    appliance_id: {
        "level": None,
        "gpio_state": None,
        "ack_received": False,
        "gpio_readback_verified": False,
        "acked_at": None,
        "verification": "NO_ACK",
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

        # Only real Pi GPIO output readback is trusted as a pin-level result.
        # Even that is NOT sensor confirmation that the appliance itself worked.
        gpio_verified = bool(hw["gpio_readback_verified"])
        if gpio_verified:
            level = int(hw["level"])
            gpio_state = int(hw["gpio_state"])
            power_w = meta["rated_w"] if gpio_state != 0 else 0.0
            controllable_w += power_w
            state_basis = "raspberry_pi_gpio_readback"
            power_estimate = round(power_w, 3)
        else:
            # Keep a display-friendly intended level, but explicitly mark it
            # unverified and do not count it as hardware-derived load.
            source_level = source.get("level")
            level = int(source_level) if source_level in (0, 1, 2) else 0
            gpio_state = None
            state_basis = (
                "accepted_command_without_gpio_readback"
                if hw["ack_received"]
                else "model_input_unverified"
            )
            power_estimate = None

        # peak_locked_out: True during active grid peak for flexible loads,
        # unless the appliance was opted out via billing confirmation.
        peak_active = (
            latest_grid_warning is not None
            and latest_grid_warning.get("action") == "active"
        )
        opted_out_ids = set(
            latest_grid_warning.get("opted_out", [])
        ) if latest_grid_warning else set()
        peak_locked = (
            peak_active
            and appliance_id in PEAK_FLEXIBLE_IDS
            and appliance_id not in opted_out_ids
        )

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
                "peak_locked_out": peak_locked,
                "power_15min_mean_w": power_estimate,
                "measured_w": None,
                "gpio_state": gpio_state,
                "gpio_readback_verified": gpio_verified,
                # No appliance-current/power sensor exists in this prototype.
                "actuation_verified": False,
                "verification_status": (
                    "GPIO_READBACK_ONLY_NOT_APPLIANCE_CONFIRMED"
                    if gpio_verified
                    else state_basis
                ),
                "state_basis": state_basis,
                "remaining_service_hours": float(
                    source.get("remaining_service_hours", 0.0) or 0.0
                ),
                "shed_reason": source.get("shed_reason"),
                "deferred_until": source.get("deferred_until"),
                "power_basis": "catalogued_estimate_only_when_gpio_readback_available",
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
                "gpio_state": "real_pi_gpio_readback_when_available_otherwise_null",
                "appliance_level": "gpio_readback_level_or_unverified_model_input",
                "actuation": "not_sensor_confirmed",
                "appliance_power": "catalogue_estimate_not_measured",
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
        # Kept at zero because there is no sensor confirming appliance operation.
        "hardware_confirmed_devices": 0,
        "gpio_readback_verified_devices": sum(
            1 for item in confirmed.values() if item["gpio_readback_verified"]
        ),
        "acknowledged_commands": sum(
            1 for item in confirmed.values() if item["ack_received"]
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
            (GRID_WARNING_TOPIC, 1),
        ]
    )

    publish_bridge_health(client)


def on_message(client, userdata, msg):
    global latest_input_state
    global latest_weather
    global latest_pi_health
    global latest_grid_event
    global latest_grid_warning
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

    if msg.topic == GRID_WARNING_TOPIC:
        latest_grid_warning = payload
        publish_runtime(client)
        return

    if "/actuator/" in msg.topic and msg.topic.endswith("/ack"):
        appliance_id = payload.get("appliance_id")

        if appliance_id not in confirmed:
            return

        if payload.get("accepted") is True:
            confirmed[appliance_id]["ack_received"] = True
            confirmed[appliance_id]["acked_at"] = payload.get(
                "acked_at", now_ist()
            )
            confirmed[appliance_id]["verification"] = payload.get(
                "verification", "UNSPECIFIED"
            )

            # Never trust an ACK from a simulated Windows agent as hardware state.
            # GPIO readback still verifies only the pin, not appliance operation.
            readback_verified = (
                payload.get("gpio_readback_verified") is True
                and payload.get("verification") == "GPIO_READBACK_ONLY"
            )
            confirmed[appliance_id]["gpio_readback_verified"] = readback_verified
            if readback_verified:
                confirmed[appliance_id]["level"] = int(
                    payload.get("applied_level", 0) or 0
                )
                confirmed[appliance_id]["gpio_state"] = int(
                    payload.get("gpio_state", 0) or 0
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
    print(f"Grid warning: {GRID_WARNING_TOPIC}")
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
