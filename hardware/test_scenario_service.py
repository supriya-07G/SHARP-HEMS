"""
Offline test for scenario_service.py: no broker, a fake MQTT client.

Usage:
  python hardware/test_scenario_service.py
"""

import json

import scenario_service as svc


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload), retain))


class FakeMsg:
    def __init__(self, payload):
        self.payload = payload


def main():
    # Only known scenarios are accepted.
    assert svc.parse_request(b'{"scenario": "household_peak"}') == "household_peak"
    assert svc.parse_request(b'{"scenario": "peak"}') == "peak"
    assert svc.parse_request(b'{"scenario": "rm -rf"}') is None
    assert svc.parse_request(b"not json") is None
    assert svc.parse_request(b'["normal"]') is None

    # Applying publishes the full HomeState and a retained report.
    client = FakeClient()
    svc.apply_scenario(client, "grid_and_household_peak")
    (t1, state, r1), (t2, active, r2) = client.published
    assert t1 == svc.STATE_TOPIC and not r1
    assert len(state["state_vector"]) == 305
    assert state["mock_scenario"] == "grid_and_household_peak"
    assert state["household_peak"] is True
    assert t2 == svc.ACTIVE_TOPIC and r2
    assert active["scenario"] == "grid_and_household_peak"
    assert active["expects_grid_peak"] is True

    # A request changes the scenario and wakes the publish loop once.
    svc.current_scenario = "normal"
    svc.scenario_changed.clear()
    svc.on_message(None, None, FakeMsg(b'{"scenario": "household_peak"}'))
    assert svc.current_scenario == "household_peak"
    assert svc.scenario_changed.is_set()

    svc.scenario_changed.clear()
    svc.on_message(None, None, FakeMsg(b'{"scenario": "household_peak"}'))
    assert not svc.scenario_changed.is_set(), "same scenario must not re-wake"

    svc.on_message(None, None, FakeMsg(b'{"scenario": "bogus"}'))
    assert svc.current_scenario == "household_peak", "bad request ignored"

    print("✅ scenario service OK")


if __name__ == "__main__":
    main()
