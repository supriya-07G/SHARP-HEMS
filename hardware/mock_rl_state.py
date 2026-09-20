"""
Dataset-contract mock HomeState publisher for SHARP.

This does NOT invent a random 305-vector. It builds the vector using the exact
feature order from scripts/generate_sharp_rl_transitions_v2.py:

  25 global features + 28 device slots x 10 features = 305.

The ten physical prototype appliances are assigned slots by device_id ascending,
which is the same ordering rule used by the training dataset generator.

Usage:
  python hardware/mock_rl_state.py --scenario normal --print-only
  python hardware/mock_rl_state.py --scenario peak --print-only
  python hardware/mock_rl_state.py --scenario normal --publish
  python hardware/mock_rl_state.py --scenario peak --publish
"""

import argparse
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

HOUSE_ID = os.getenv("HOUSE_ID", "demo")
MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

STATE_TOPIC = f"home/{HOUSE_ID}/state"
IST = ZoneInfo("Asia/Kolkata")

GLOBAL_FEATURES = [
    "obs_T2M",
    "obs_RH2M",
    "obs_ALLSKY_SFC_SW_DWN",
    "obs_WS10M",
    "obs_grid_percentile",
    "obs_grid_peak_severity",
    "fraction_of_day",
    "month_to_date_kwh_div500",
    "connection_limit_kw",
    "indoor_temperature_c_div50",
    "degrees_above_comfort_band",
    "degrees_below_comfort_band",
    "household_has_air_conditioner",
    "occupancy_adult_home_fraction",
    "attention_available",
    "marginal_tariff_inr_kwh_div10",
    "mode_grid_import",
    "mode_self_sufficient",
    "mode_islanded",
    "self_sufficient_fraction",
    "battery_state_of_charge",
    "pv_generation_kw",
    "unserved_demand_kw",
    "grid_absent",
    "recent_override_count_div10",
]

DEVICE_FEATURES = [
    "remaining_service_hours",
    "power_proxy_kw",
    "current_on",
    "protected_service",
    "cycle_type",
    "elapsed_state_steps_divided_by_96",
    "preferred_service_fraction",
    "is_air_conditioner",
    "steps_since_shed_div96",
    "device_override_count_div10",
]

MAX_DEVICES = 28

# Dataset slot rule: device_id ascending within one household.
DEVICE_ORDER = sorted([
    "air_conditioner_01",
    "refrigerator_01",
    "washing_machine_01",
    "mixer_grinder_01",
    "television_01",
    "ev_charger_01",
    "led_bulb_01",
    "led_tube_01",
    "table_fan_01",
    "ceiling_fan_01",
])

DEVICE_META = {
    "air_conditioner_01": {
        "display_name": "Air Conditioner",
        "appliance_type": "air_conditioner",
        "service_class": "thermostatic",
        "is_necessity": False,
        "supports_reduced": False,
        "power_kw": 1.3284,
        "remaining_h": 4.0,
        "cycle_type": 0.0,
        "is_ac": 1.0,
    },
    "ceiling_fan_01": {
        "display_name": "Motor Fan",
        "appliance_type": "ceiling_fan",
        "service_class": "critical",
        "is_necessity": True,
        "supports_reduced": False,
        "power_kw": 0.0600,
        "remaining_h": 4.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "ev_charger_01": {
        "display_name": "EV Charger",
        "appliance_type": "ev_charger",
        "service_class": "deferrable",
        "is_necessity": False,
        "supports_reduced": False,
        "power_kw": 0.7000,
        "remaining_h": 3.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "led_bulb_01": {
        "display_name": "Light 1",
        "appliance_type": "led_bulb",
        "service_class": "critical",
        "is_necessity": True,
        "supports_reduced": False,
        "power_kw": 0.0090,
        "remaining_h": 3.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "led_tube_01": {
        "display_name": "Light 2",
        "appliance_type": "led_tube",
        "service_class": "critical",
        "is_necessity": True,
        "supports_reduced": False,
        "power_kw": 0.0200,
        "remaining_h": 3.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "mixer_grinder_01": {
        "display_name": "Mixer Grinder",
        "appliance_type": "mixer_grinder",
        "service_class": "interruptible",
        "is_necessity": False,
        "supports_reduced": False,
        "power_kw": 0.5000,
        "remaining_h": 0.25,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "refrigerator_01": {
        "display_name": "Refrigerator",
        "appliance_type": "refrigerator",
        "service_class": "critical",
        "is_necessity": True,
        "supports_reduced": False,
        "power_kw": 0.0432,
        "remaining_h": 12.0,
        "cycle_type": 1.0,
        "is_ac": 0.0,
    },
    "table_fan_01": {
        "display_name": "USB Fan",
        "appliance_type": "table_fan",
        "service_class": "critical",
        "is_necessity": True,
        "supports_reduced": False,
        "power_kw": 0.0400,
        "remaining_h": 4.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "television_01": {
        "display_name": "Television",
        "appliance_type": "television",
        "service_class": "interruptible",
        "is_necessity": False,
        "supports_reduced": False,
        "power_kw": 0.0800,
        "remaining_h": 2.0,
        "cycle_type": 0.0,
        "is_ac": 0.0,
    },
    "washing_machine_01": {
        "display_name": "Washing Machine",
        "appliance_type": "washing_machine",
        "service_class": "deferrable",
        "is_necessity": False,
        "supports_reduced": False,
        "power_kw": 0.1137,
        "remaining_h": 1.0,
        "cycle_type": 1.0,
        "is_ac": 0.0,
    },
}

SCENARIOS = {
    "normal": {
        "step_id": 50,
        "outdoor_c": 35.2,
        "rh_pct": 55.0,
        "solar_wm2": 650.0,
        "wind_ms": 2.2,
        "grid_percentile": 0.45,
        "grid_peak_severity": 0.15,
        "month_to_date_kwh": 96.4,
        "sanctioned_kw": 1.0,
        "indoor_c": 30.8,
        "occupancy_fraction": 0.83,
        "attention": True,
        "tariff_inr_kwh": 4.50,
        "battery_soc": 0.85,
        "background_kw": 0.084,
        "current": {
            "air_conditioner_01": 1,
            "ceiling_fan_01": 1,
            "ev_charger_01": 0,
            "led_bulb_01": 1,
            "led_tube_01": 1,
            "mixer_grinder_01": 0,
            "refrigerator_01": 1,
            "table_fan_01": 0,
            "television_01": 1,
            "washing_machine_01": 1,
        },
        "wanted": {
            "air_conditioner_01": True,
            "ceiling_fan_01": True,
            "ev_charger_01": False,
            "led_bulb_01": True,
            "led_tube_01": True,
            "mixer_grinder_01": False,
            "refrigerator_01": True,
            "table_fan_01": False,
            "television_01": True,
            "washing_machine_01": True,
        },
    },
    "peak": {
        "step_id": 56,
        "outdoor_c": 36.8,
        "rh_pct": 53.0,
        "solar_wm2": 780.0,
        "wind_ms": 1.8,
        "grid_percentile": 0.93,
        "grid_peak_severity": 0.67,
        "month_to_date_kwh": 96.9,
        "sanctioned_kw": 1.0,
        "indoor_c": 31.4,
        "occupancy_fraction": 0.83,
        "attention": True,
        "tariff_inr_kwh": 4.50,
        "battery_soc": 0.78,
        "background_kw": 0.084,
        # Deliberately start several discretionary loads ON so the policy has
        # something meaningful to decide under a peak.
        "current": {
            "air_conditioner_01": 1,
            "ceiling_fan_01": 1,
            "ev_charger_01": 1,
            "led_bulb_01": 1,
            "led_tube_01": 1,
            "mixer_grinder_01": 1,
            "refrigerator_01": 1,
            "table_fan_01": 1,
            "television_01": 1,
            "washing_machine_01": 1,
        },
        "wanted": {
            "air_conditioner_01": True,
            "ceiling_fan_01": True,
            "ev_charger_01": False,
            "led_bulb_01": True,
            "led_tube_01": True,
            "mixer_grinder_01": False,
            "refrigerator_01": True,
            "table_fan_01": True,
            "television_01": True,
            "washing_machine_01": True,
        },
    },
}


def device_vector(appliance_id, current_on, wanted):
    meta = DEVICE_META[appliance_id]
    # Dataset features are RAW here. pi_agent.py applies the train-only
    # normalisation shipped inside the PKL.
    elapsed_steps = 8 if current_on else 4
    steps_since_shed = 0 if current_on else 20

    return [
        float(meta["remaining_h"]),
        float(meta["power_kw"]),
        float(current_on),
        float(meta["is_necessity"]),
        float(meta["cycle_type"]),
        float(elapsed_steps) / 96.0,
        1.0 if wanted else 0.0,
        float(meta["is_ac"]),
        float(steps_since_shed) / 96.0,
        0.0,
    ]


def build_mock_home_state(scenario_name):
    cfg = SCENARIOS[scenario_name]
    comfort_low, comfort_high = 22.0, 30.0
    indoor = float(cfg["indoor_c"])

    globals_ = [
        float(cfg["outdoor_c"]),
        float(cfg["rh_pct"]),
        float(cfg["solar_wm2"]),
        float(cfg["wind_ms"]),
        float(cfg["grid_percentile"]),
        float(cfg["grid_peak_severity"]),
        float(cfg["step_id"]) / 96.0,
        float(cfg["month_to_date_kwh"]) / 500.0,
        float(cfg["sanctioned_kw"]),
        indoor / 50.0,
        max(0.0, indoor - comfort_high),
        max(0.0, comfort_low - indoor),
        1.0,
        float(cfg["occupancy_fraction"]),
        1.0 if cfg["attention"] else 0.0,
        float(cfg["tariff_inr_kwh"]) / 10.0,
        1.0,  # mode_grid_import
        0.0,  # mode_self_sufficient
        0.0,  # mode_islanded
        0.0,  # self_sufficient_fraction
        float(cfg["battery_soc"]),
        0.0,  # pv_generation_kw (main training scenario)
        0.0,  # unserved_demand_kw
        0.0,  # grid_absent
        0.0,  # recent_override_count_div10
    ]

    assert len(globals_) == 25

    vector = list(globals_)
    appliances = []

    for slot, appliance_id in enumerate(DEVICE_ORDER):
        meta = DEVICE_META[appliance_id]
        current_on = int(cfg["current"][appliance_id])
        wanted = bool(cfg["wanted"][appliance_id])

        vector.extend(
            device_vector(
                appliance_id,
                current_on,
                wanted,
            )
        )

        appliances.append({
            "appliance_id": appliance_id,
            "display_name": meta["display_name"],
            "appliance_type": meta["appliance_type"],
            "service_class": meta["service_class"],
            "is_necessity": meta["is_necessity"],
            "supports_reduced": meta["supports_reduced"],
            "level": current_on,
            "occupant_wants": wanted,
            # Keep false in the inference test: the model gets to decide.
            # The Pi's independent safety shield still protects necessities.
            "peak_locked_out": False,
            "power_15min_mean_w": float(meta["power_kw"]) * 1000.0 if current_on else 0.0,
            "measured_w": None,
            "gpio_state": 1 if current_on else 0,
            "actuation_verified": False,
            "remaining_service_hours": float(meta["remaining_h"]),
            "slot": slot,
        })

    # Remaining dataset slots are zero-padded exactly like the generator.
    for _ in range(MAX_DEVICES - len(DEVICE_ORDER)):
        vector.extend([0.0] * len(DEVICE_FEATURES))

    assert len(vector) == 305, len(vector)

    aggregate = float(cfg["background_kw"])
    for app in appliances:
        if app["level"]:
            aggregate += app["power_15min_mean_w"] / 1000.0

    return {
        "schema_version": "sharp_home_state_mock_v2",
        "house_id": HOUSE_ID,
        "timestamp_ist": datetime.now(IST).isoformat(),
        "step_id": int(cfg["step_id"]),
        "aggregate_power_kw": round(aggregate, 4),
        "background_load_kw": float(cfg["background_kw"]),
        "sanctioned_load_kw": float(cfg["sanctioned_kw"]),
        "indoor_temperature_c": indoor,
        "outdoor_temperature_c": float(cfg["outdoor_c"]),
        "occupancy_adult_home_fraction": float(cfg["occupancy_fraction"]),
        "attention_available": bool(cfg["attention"]),
        "marginal_tariff_inr_kwh": float(cfg["tariff_inr_kwh"]),
        "month_to_date_kwh": float(cfg["month_to_date_kwh"]),
        "grid_peak_severity": float(cfg["grid_peak_severity"]),
        "operating_mode": "grid_import",
        "battery_state_of_charge": float(cfg["battery_soc"]),
        "grid_absent": False,
        "state_vector": vector,
        "appliances": appliances,
        "mock_source": "SHARP_RL_TRANSITIONS_V2_FEATURE_SCHEMA",
        "mock_scenario": scenario_name,
        "device_slot_rule": "device_id ascending within household",
        "physical_device_count": len(DEVICE_ORDER),
    }


def publish(payload):
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
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sharp-mock-state-{int(time.time())}",
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    connected = {"ok": False}

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            connected["ok"] = True
        else:
            raise RuntimeError(f"MQTT connect failed: {reason_code}")

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    deadline = time.time() + 10
    while not connected["ok"] and time.time() < deadline:
        time.sleep(0.05)

    if not connected["ok"]:
        client.loop_stop()
        client.disconnect()
        raise TimeoutError("MQTT connection timed out")

    info = client.publish(
        STATE_TOPIC,
        json.dumps(payload),
        qos=1,
        retain=False,
    )
    info.wait_for_publish(timeout=10)

    client.loop_stop()
    client.disconnect()

    print(f"✅ Published 10-device mock HomeState → {STATE_TOPIC}")
    print(f"   scenario: {payload['mock_scenario']}")
    print(f"   features: {len(payload['state_vector'])}")
    print("   slots:")
    for app in payload["appliances"]:
        print(f"     {app['slot']:02d}  {app['appliance_id']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="peak",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-only", action="store_true")
    mode.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    payload = build_mock_home_state(args.scenario)

    if args.print_only:
        print(json.dumps(payload, indent=2))
        print()
        print(f"✅ Feature count: {len(payload['state_vector'])}")
        print(f"✅ Device count: {len(payload['appliances'])}")
        return

    publish(payload)


if __name__ == "__main__":
    main()
