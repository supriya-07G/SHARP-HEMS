"""
Offline smoke test for the pre-peak warning and billing opt-out flow.

No broker, no GPIO. A fake MQTT client records what pi_agent publishes on
home/<house>/grid/warning, and runtime_bridge is fed those messages to check
peak_locked_out. The warning is shortened to 1 s.

Usage:
  python hardware/test_peak_warning.py
"""

import json
import os
import time

os.environ["PEAK_WARNING_SECONDS"] = "1"
os.environ["GPIO_ENABLED"] = "false"
os.environ["OLED_ENABLED"] = "false"

import pi_agent  # noqa: E402
import runtime_bridge  # noqa: E402
from mock_rl_state import build_mock_home_state  # noqa: E402


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload)))

    def warnings(self):
        return [
            p for t, p in self.published
            if t == pi_agent.GRID_WARNING_TOPIC
        ]


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = json.dumps(payload).encode()


def declare(client, severity=0.85):
    pi_agent.handle_grid_event(client, json.dumps({
        "schema_version": "sharp_grid_event_v1",
        "action": "declare",
        "severity": severity,
    }))


def locked_ids(warning):
    runtime_bridge.on_message(
        FakeClient(), None,
        FakeMsg(runtime_bridge.GRID_WARNING_TOPIC, warning),
    )
    state = runtime_bridge.build_runtime_state()
    return {
        a["appliance_id"] for a in state["appliances"]
        if a["peak_locked_out"]
    }


def main():
    client = FakeClient()

    runtime_bridge.on_message(
        FakeClient(), None,
        FakeMsg(runtime_bridge.STATE_TOPIC, build_mock_home_state("peak")),
    )

    declare(client)
    first = client.warnings()[-1]
    assert pi_agent.peak_phase == "WARNING"
    assert first["action"] == "warning"
    assert first["shed_at"] and first["warning_started_at"]
    assert first["lead_time_seconds"] == 1
    assert locked_ids(first) == set(), "nothing is locked during the warning"

    # A severity update must not restart the countdown.
    declare(client, 0.9)
    assert len(client.warnings()) == 1

    # Resident accepts the surcharge for the AC.
    pi_agent.handle_override(client, json.dumps({
        "appliance_id": "air_conditioner_01",
        "requested_level": 1,
    }))
    opt = client.warnings()[-1]
    assert opt["action"] == "warning"
    assert opt["opted_out"] == ["air_conditioner_01"]
    assert opt["warning_started_at"] == first["warning_started_at"]

    time.sleep(1.5)
    active = client.warnings()[-1]
    assert pi_agent.peak_phase == "ACTIVE"
    assert active["action"] == "active"
    assert active["opted_out"] == ["air_conditioner_01"]
    locked = locked_ids(active)
    assert "air_conditioner_01" not in locked
    assert {"ev_charger_01", "television_01"} <= locked
    assert not locked & {
        a for a, d in pi_agent.DEVICES.items() if d["necessity"]
    }

    # Opt-out after shedding started must unlock that appliance too.
    pi_agent.handle_override(client, json.dumps({
        "appliance_id": "ev_charger_01",
        "requested_level": 1,
    }))
    late = client.warnings()[-1]
    assert late["action"] == "active"
    assert "ev_charger_01" not in locked_ids(late)

    lines = pi_agent.oled_peak_page()
    assert lines[1] == "PEAK ACTIVE (SHED)"
    assert all(len(line) <= 21 for line in lines), lines

    pi_agent.handle_grid_event(client, json.dumps({"action": "cancel"}))
    cancel = client.warnings()[-1]
    assert pi_agent.peak_phase == "NONE"
    assert cancel["action"] == "cancel"
    # The cancel still names the event, so the dashboard can close it out.
    assert cancel["warning_started_at"] == first["warning_started_at"]
    assert cancel["opted_out"] == ["air_conditioner_01", "ev_charger_01"]
    assert locked_ids(cancel) == set()

    # The event's duration running out ends the peak without a Cancel.
    expires = (
        pi_agent.datetime.now(pi_agent.timezone.utc)
        + pi_agent.timedelta(seconds=2)
    ).isoformat()
    pi_agent.handle_grid_event(client, json.dumps({
        "action": "declare", "severity": 0.85, "expires_at": expires,
    }))
    time.sleep(1.5)
    assert pi_agent.peak_phase == "ACTIVE"
    time.sleep(1.0)
    assert pi_agent.peak_phase == "NONE", "expired event must end the peak"
    assert client.warnings()[-1]["action"] == "cancel"
    assert pi_agent.active_grid_event is None

    # A low-severity declare during a warning ends it and stops the timer.
    declare(client)
    declare(client, 0.3)
    assert pi_agent.peak_phase == "NONE"
    time.sleep(1.5)
    assert pi_agent.peak_phase == "NONE", "cancelled timer must not fire"

    print("✅ peak warning flow OK")


if __name__ == "__main__":
    main()
