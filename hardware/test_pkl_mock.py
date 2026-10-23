"""
Offline PKL smoke test using the exact SHARP 305-feature mock contract.

This does NOT touch MQTT or GPIO. It proves:
  1) the PKL loads,
  2) the 305 -> BDQ forward pass runs,
  3) legal actions are produced for the six prototype appliances,
  4) changing normal -> peak input changes the Q-values,
  5) the luxury peak policy gives the four scenario outcomes:
       grid+household peak -> luxury shed
       grid peak only      -> luxury shed
       household peak only -> luxury shed
       neither             -> luxury never shed, even one the resident
                              switched on

Usage:
  python hardware/test_pkl_mock.py
"""

import numpy as np

from pi_agent import (
    DEVICES,
    GPIO_PINS,
    LEVEL_NAMES,
    N_BRANCHES,
    PklSharpPolicy,
    PKL_MODEL_PATH,
    PEAK_FLEXIBLE_LOADS,
    apply_luxury_peak_policy,
)

from mock_rl_state import (
    DEVICE_ORDER,
    build_mock_home_state,
)


def masks(payload):
    present = np.zeros(N_BRANCHES, dtype=bool)
    necessity = np.zeros(N_BRANCHES, dtype=bool)
    reduced = np.zeros(N_BRANCHES, dtype=bool)
    wanted = np.zeros(N_BRANCHES, dtype=bool)

    for app in payload["appliances"]:
        appliance_id = app["appliance_id"]
        if appliance_id not in GPIO_PINS:
            continue

        slot = int(app["slot"])
        present[slot] = True
        necessity[slot] = bool(DEVICES[appliance_id]["necessity"])
        reduced[slot] = bool(DEVICES[appliance_id]["supports_reduced"])
        wanted[slot] = bool(app["occupant_wants"])

    return present, necessity, reduced, wanted


# Grid peak is declared from the dashboard; here it is set as it would be
# once the declared peak has passed its 10-minute warning.
GRID_SHED = {
    "normal": False,
    "grid_peak": True,
    "household_peak": False,
    "grid_and_household_peak": True,
}


def evaluate(policy, scenario, resident_on=()):
    payload = build_mock_home_state(scenario)
    state = np.asarray(payload["state_vector"], dtype=float)
    present, necessity, reduced, wanted = masks(payload)

    actions, q = policy.decide(
        state,
        present,
        necessity,
        reduced,
        wanted,
    )

    print()
    print("=" * 72)
    print(f"SCENARIO: {scenario.upper()}")
    print("=" * 72)

    for app in payload["appliances"]:
        appliance_id = app["appliance_id"]
        slot = int(app["slot"])
        action = int(actions[slot])
        qtxt = ", ".join(
            f"{LEVEL_NAMES[level]}={q[slot, level]:.4f}"
            for level in range(3)
        )
        print(
            f"slot {slot:02d} | {appliance_id:<24} "
            f"-> {LEVEL_NAMES[action]:<7} | {qtxt}"
        )

    slot_to_appliance = {int(app["slot"]): app for app in payload["appliances"] if app["appliance_id"] in GPIO_PINS}
    live_levels = {
        app["appliance_id"]: max(
            int(app["level"]),
            1 if app["appliance_id"] in resident_on else 0,
        )
        for app in payload["appliances"]
    }
    effective_actions, overrides = apply_luxury_peak_policy(
        actions,
        slot_to_appliance,
        live_levels,
        GRID_SHED[scenario],
        bool(payload["household_peak"]),
        set(),
    )
    if overrides:
        print("LUXURY PEAK POLICY OVERRIDES:", overrides)
    print("Effective physical-rig actions:", {app["appliance_id"]: LEVEL_NAMES[int(effective_actions[int(app["slot"])])] for app in payload["appliances"] if app["appliance_id"] in GPIO_PINS})
    return q, actions, payload, effective_actions


def main():
    print(f"Loading: {PKL_MODEL_PATH}")
    policy = PklSharpPolicy(PKL_MODEL_PATH)

    q_normal, a_normal, normal, effective_normal = evaluate(policy, "normal")
    q_peak, a_peak, peak, effective_peak = evaluate(policy, "grid_peak")

    delta = float(np.max(np.abs(q_peak - q_normal)))

    print()
    print("=" * 72)
    print("MODEL CHECK")
    print("=" * 72)
    print("Input width       :", len(normal["state_vector"]))
    print("Q output shape    :", q_normal.shape)
    print("Max Q change      :", f"{delta:.8f}")
    print(
        "Changed actions   :",
        int(np.sum(a_normal != a_peak)),
        "of",
        N_BRANCHES,
        "branches (raw PKL)",
    )

    if q_normal.shape != (28, 3):
        raise AssertionError(f"Expected Q shape (28, 3), got {q_normal.shape}")

    if delta <= 1e-9:
        raise AssertionError(
            "Normal and peak inputs produced identical Q-values; "
            "the model is not responding to the changed state."
        )

    for payload, actions in ((normal, a_normal), (peak, a_peak)):
        for app in payload["appliances"]:
            slot = int(app["slot"])
            action = int(actions[slot])
            if action == 2:
                raise AssertionError(
                    f"{app['appliance_id']} selected REDUCED even though "
                    "the current hardware declares supports_reduced=False"
                )
            if (
                app["is_necessity"]
                and app["occupant_wants"]
                and action == 0
            ):
                raise AssertionError(
                    f"Safety mask allowed necessity shed: {app['appliance_id']}"
                )

    def luxury_levels(payload, actions):
        return {
            app["appliance_id"]: int(actions[int(app["slot"])])
            for app in payload["appliances"]
            if app["appliance_id"] in PEAK_FLEXIBLE_LOADS
        }

    print()
    print("=" * 72)
    print("FOUR SCENARIOS")
    print("=" * 72)

    for scenario in ("grid_and_household_peak", "grid_peak", "household_peak"):
        _, _, payload, effective = evaluate(policy, scenario)
        luxury = luxury_levels(payload, effective)
        if any(luxury.values()):
            raise AssertionError(f"{scenario}: luxury loads not shed: {luxury}")
        print(f"✅ {scenario}: all luxury loads shed")

    # Normal: the resident switched the AC and EV on. No peak -> they stay on.
    _, _, payload, effective = evaluate(
        policy, "normal", resident_on=("air_conditioner_01", "ev_charger_01"),
    )
    luxury = luxury_levels(payload, effective)
    expected_on = {"air_conditioner_01", "ev_charger_01", "television_01"}
    off = sorted(a for a in expected_on if not luxury[a])
    if off:
        raise AssertionError(f"normal: luxury loads shed with no peak: {off}")
    print("✅ normal: AC, EV and TV stay on with no peak")

    print()
    print("✅ PKL MOCK INFERENCE TEST PASSED")
    print("The model loads, produces 28x3 Q-values, responds to state changes,")
    print("and the deployment mask keeps the prototype actions legal.")


if __name__ == "__main__":
    main()
