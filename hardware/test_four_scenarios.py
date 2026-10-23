"""
End-to-end check of the four peak scenarios through pi_agent's MQTT handlers.

The real PKL model runs; MQTT and GPIO are faked. The grid peak is declared
as the dashboard's Grid Controller would, with the warning shortened to 1 s.

  grid peak  household peak  luxury loads
  yes        yes             shed
  yes        no              shed (after the warning)
  no         yes             shed, this house only
  no         no              never shed, even ones the resident switched on

In every peak a resident who pays the surcharge keeps that load on.

Usage:
  python hardware/test_four_scenarios.py
"""

import json
import os
import time

os.environ["PEAK_WARNING_SECONDS"] = "1"
os.environ["GPIO_ENABLED"] = "false"
os.environ["OLED_ENABLED"] = "false"
os.environ["RL_ENABLED"] = "true"

import pi_agent  # noqa: E402
from mock_rl_state import build_mock_home_state  # noqa: E402

LUXURY = sorted(pi_agent.PEAK_FLEXIBLE_LOADS)
ESSENTIAL = ["ceiling_fan_01", "led_bulb_01", "led_tube_01", "refrigerator_01"]


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload)))

    def last_status(self):
        for topic, payload in reversed(self.published):
            if topic == pi_agent.GRID_WARNING_TOPIC:
                return payload
        return None


class FakeMsg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = json.dumps(payload).encode()


def send_state(client, scenario):
    pi_agent.on_message(
        client, None,
        FakeMsg(pi_agent.STATE_TOPIC, build_mock_home_state(scenario)),
    )


def grid_event(client, action, severity=None):
    event = {"schema_version": "sharp_grid_event_v1", "action": action}
    if severity is not None:
        event["severity"] = severity
    pi_agent.on_message(client, None, FakeMsg(pi_agent.GRID_EVENT_TOPIC, event))


def resident(client, appliance_id, level):
    pi_agent.handle_override(client, json.dumps({
        "appliance_id": appliance_id,
        "requested_level": level,
    }))
    # Let the RL loop act on it again straight away, as after the hold.
    pi_agent.manual_override_until.clear()


def on(*ids):
    return {a for a in ids if pi_agent.current_levels[a] != 0}


def expect(label, on_ids, off_ids):
    wrong_off = sorted(set(on_ids) - on(*on_ids))
    wrong_on = sorted(on(*off_ids))
    assert not wrong_off and not wrong_on, (
        f"{label}: should be ON but OFF {wrong_off}; "
        f"should be OFF but ON {wrong_on}"
    )
    print(f"✅ {label}")


def main():
    pi_agent.rl_policy = pi_agent.PklSharpPolicy(pi_agent.PKL_MODEL_PATH)
    client = FakeClient()

    # 1) No grid peak, no household peak.
    send_state(client, "normal")
    expect(
        "normal: fridge, TV, fan and lights on",
        ESSENTIAL + ["television_01"],
        ["air_conditioner_01", "ev_charger_01"],
    )
    resident(client, "air_conditioner_01", 1)
    resident(client, "ev_charger_01", 1)
    send_state(client, "normal")
    expect(
        "normal: resident's AC and EV stay on (no peak, not shed)",
        ESSENTIAL + ["television_01", "air_conditioner_01", "ev_charger_01"],
        [],
    )
    assert client.last_status() is None, "no peak status in normal"

    # 2) Household peak, no grid peak.
    send_state(client, "household_peak")
    assert client.last_status()["action"] == "household"
    expect("household peak: luxury shed, essentials on", ESSENTIAL, LUXURY)

    resident(client, "air_conditioner_01", 1)
    assert client.last_status()["opted_out"] == ["air_conditioner_01"]
    send_state(client, "household_peak")
    expect(
        "household peak: paid AC stays on, rest shed",
        ESSENTIAL + ["air_conditioner_01"],
        [a for a in LUXURY if a != "air_conditioner_01"],
    )

    send_state(client, "normal")
    status = client.last_status()
    assert status["action"] == "cancel"
    assert status["opted_out"] == ["air_conditioner_01"]
    assert pi_agent.peak_opted_out == set()
    # Back to the house state: the TV returns; the paid AC stays on; the EV
    # the peak shed stays off until the resident switches it on again.
    expect(
        "household peak ended: TV back on, paid AC still on, EV stays off",
        ESSENTIAL + ["television_01", "air_conditioner_01"],
        ["ev_charger_01"],
    )

    # 3) Grid peak, no household peak. All on until the dashboard declares.
    send_state(client, "grid_peak")
    expect("grid scenario before declare: everything on", ESSENTIAL + LUXURY, [])

    grid_event(client, "declare", 0.85)
    assert client.last_status()["action"] == "warning"
    expect("grid warning: luxury still on for 10 min", ESSENTIAL + LUXURY, [])

    resident(client, "ev_charger_01", 1)
    time.sleep(1.5)
    assert client.last_status()["action"] == "active"
    expect(
        "grid peak active: luxury shed except paid EV",
        ESSENTIAL + ["ev_charger_01"],
        [a for a in LUXURY if a != "ev_charger_01"],
    )

    grid_event(client, "cancel")
    assert client.last_status()["action"] == "cancel"
    expect("grid peak cancelled: luxury back on", ESSENTIAL + LUXURY, [])

    # 4) Grid peak + household peak. Household sheds at once, even in the
    #    grid warning; the episode stays open until both end.
    send_state(client, "grid_and_household_peak")
    assert client.last_status()["action"] == "household"
    expect("grid+household: luxury shed", ESSENTIAL, LUXURY)

    grid_event(client, "declare", 0.85)
    assert client.last_status()["action"] == "warning"
    expect("grid+household during grid warning: still shed", ESSENTIAL, LUXURY)

    time.sleep(1.5)
    assert client.last_status()["action"] == "active"
    expect("grid+household active: luxury shed", ESSENTIAL, LUXURY)

    grid_event(client, "cancel")
    assert client.last_status()["action"] == "household", (
        "household peak continues after the grid peak ends"
    )
    expect("grid cancelled, household peak continues: shed", ESSENTIAL, LUXURY)

    send_state(client, "normal")
    assert client.last_status()["action"] == "cancel"
    expect(
        "both ended: back to normal",
        ESSENTIAL + ["television_01"],
        [],
    )

    print()
    print("✅ FOUR SCENARIOS PASSED")


if __name__ == "__main__":
    main()
