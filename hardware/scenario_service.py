"""
SHARP scenario service - the dashboard chooses the house scenario.

Runs on the Raspberry Pi beside pi_agent.py and runtime_bridge.py, started at
boot by systemd, so nobody has to SSH in to run mock_rl_state.py.

  dashboard --(retained) home/<house>/scenario/set--> this service
  this service --home/<house>/state--> pi_agent.py, runtime_bridge.py
  this service --(retained) home/<house>/scenario/active--> dashboard

The state is built by mock_rl_state.build_mock_home_state(), exactly as the
command-line publisher builds it. It is published as soon as the scenario
changes, then again every SCENARIO_REPUBLISH_SECONDS so the RL loop and the
dashboard stay fresh. The request topic is retained, so after a reboot the
Pi resumes the last scenario chosen; with none chosen yet it applies
DEFAULT_SCENARIO ("normal"), so the dashboard comes alive as soon as the Pi
boots.

Usage:
  python hardware/scenario_service.py
"""

import json
import os
import socket
import ssl
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from mock_rl_state import (
    HOUSE_ID,
    IST,
    MQTT_HOST,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_TRANSPORT,
    MQTT_USER,
    MQTT_WS_PATH,
    SCENARIOS,
    STATE_TOPIC,
    build_mock_home_state,
)

SET_TOPIC = f"home/{HOUSE_ID}/scenario/set"
ACTIVE_TOPIC = f"home/{HOUSE_ID}/scenario/active"

REPUBLISH_SECONDS = float(os.getenv("SCENARIO_REPUBLISH_SECONDS", "30"))
DEFAULT_SCENARIO = os.getenv("DEFAULT_SCENARIO", "normal")

# How long to wait for a retained request after connecting before falling
# back to the default.
RETAINED_WAIT_SECONDS = 3.0

state_lock = threading.Lock()
current_scenario = None
scenario_changed = threading.Event()


def now_ist():
    return datetime.now(IST).isoformat()


def parse_request(payload_bytes):
    """Scenario name from a request, or None if it is not a known one."""
    try:
        request = json.loads(payload_bytes)
    except (TypeError, ValueError):
        return None
    if not isinstance(request, dict):
        return None
    name = request.get("scenario")
    return name if name in SCENARIOS else None


def apply_scenario(client, name):
    """Publish the scenario's HomeState and report it as active."""
    payload = build_mock_home_state(name)
    client.publish(STATE_TOPIC, json.dumps(payload), qos=1, retain=False)
    client.publish(
        ACTIVE_TOPIC,
        json.dumps({
            "schema_version": "sharp_scenario_active_v1",
            "house_id": HOUSE_ID,
            "scenario": name,
            "household_peak": bool(payload["household_peak"]),
            "expects_grid_peak": bool(payload["expects_grid_peak"]),
            "applied_at": now_ist(),
            "republish_seconds": REPUBLISH_SECONDS,
        }),
        qos=1,
        retain=True,
    )


def connect_with_retry(client, host, port, keepalive):
    """Connect to the broker, waiting out a missing network instead of exiting.

    A Pi on Wi-Fi often starts before DNS works. paho's connect() raises on
    that first attempt - reconnect_delay_set only covers drops after a
    successful connect - so without this the service would die at boot.
    """
    delay = 2
    while True:
        try:
            client.connect(host, port, keepalive=keepalive)
            return
        except socket.gaierror:
            print(
                f"🌐 Cannot resolve {host}: this machine has no working DNS. "
                f"Retrying in {delay}s (Ctrl-C to stop)"
            )
        except OSError as exc:
            print(
                f"🌐 Cannot reach {host}:{port} ({exc}). "
                f"Retrying in {delay}s (Ctrl-C to stop)"
            )
        time.sleep(delay)
        delay = min(delay * 2, 30)


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"🔌 MQTT CONNECT: {reason_code}")
    if reason_code == 0:
        client.subscribe(SET_TOPIC, qos=1)
        print(f"📡 Subscribed → {SET_TOPIC}")


def on_message(client, userdata, msg):
    global current_scenario

    name = parse_request(msg.payload)
    if name is None:
        print(f"⏭️ Ignoring scenario request: {msg.payload[:120]!r}")
        return

    with state_lock:
        changed = name != current_scenario
        current_scenario = name

    if changed:
        print(f"🎬 Scenario requested → {name}")
        scenario_changed.set()


def main():
    global current_scenario

    missing = [
        name for name, value in (
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
        client_id=f"sharp-scenario-service-{HOUSE_ID}",
        transport=MQTT_TRANSPORT,
    )
    if MQTT_TRANSPORT == "websockets":
        client.ws_set_options(path=MQTT_WS_PATH)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_message = on_message

    print("=" * 68)
    print("SHARP SCENARIO SERVICE")
    print("=" * 68)
    print(f"Broker   : {MQTT_HOST}:{MQTT_PORT} ({MQTT_TRANSPORT})")
    print(f"House    : {HOUSE_ID}")
    print(f"Requests : {SET_TOPIC}")
    print(f"State    : {STATE_TOPIC} every {REPUBLISH_SECONDS:g}s")
    print(f"Reports  : {ACTIVE_TOPIC}")
    print(f"Default  : {DEFAULT_SCENARIO}")
    print("=" * 68)

    try:
        connect_with_retry(client, MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()

        # A retained request from the dashboard arrives right after the
        # subscribe; without one, start from the default.
        deadline = time.monotonic() + RETAINED_WAIT_SECONDS
        while time.monotonic() < deadline:
            with state_lock:
                if current_scenario is not None:
                    break
            time.sleep(0.1)

        with state_lock:
            if current_scenario is None:
                current_scenario = DEFAULT_SCENARIO
                print(f"🎬 No scenario chosen yet → {DEFAULT_SCENARIO}")

        while True:
            scenario_changed.clear()
            with state_lock:
                name = current_scenario
            apply_scenario(client, name)
            print(f"📤 {name} → {STATE_TOPIC}")
            scenario_changed.wait(REPUBLISH_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Stopping scenario service...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
