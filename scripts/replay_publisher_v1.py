"""Replay a recorded SHARP household day over MQTT.

Integration flow:

    replay_publisher_v1.py
            |
            | home/demo/state
            v
         HiveMQ
            |
            v
      rl/mqtt_agent.py
            |
            | home/demo/intent
            | home/demo/actuator/<id>/cmd
            v
         HiveMQ
            |
            v
     Raspberry Pi agent

The replay publisher provides realistic 305-feature observations.
It does NOT make the live control decision during integration testing.
The RL MQTT agent is responsible for live BDQ inference.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from dotenv import load_dotenv


# ============================================================
# PATHS + ENVIRONMENT
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent),
)

# Load:
#
# C:\Users\SUPRIYA\SHARP_Master_Dataset\.env
#
load_dotenv(
    ROOT / ".env"
)


# ============================================================
# MQTT CONFIG FROM .env
# ============================================================

MQTT_HOST = os.getenv(
    "MQTT_HOST"
)

MQTT_PORT = os.getenv(
    "MQTT_PORT",
    "8883",
)

MQTT_USER = os.getenv(
    "MQTT_USER"
)

MQTT_PASS = os.getenv(
    "MQTT_PASS"
)

HOUSE_ID = os.getenv(
    "HOUSE_ID",
    "demo",
)


def default_mqtt_broker():
    """Build mqtts:// URL from root .env."""

    if not MQTT_HOST:
        return None

    return (
        f"mqtts://"
        f"{MQTT_HOST}:"
        f"{MQTT_PORT}"
    )


# ============================================================
# OPTIONAL OLD/STANDALONE POLICY
# ============================================================

def load_sharp_policy():
    """
    Load the previously shipped standalone policy.

    This is NOT used by default in the current HiveMQ integration,
    because rl/mqtt_agent.py performs the live BDQ inference.
    """

    bundle = (
        ROOT
        / "handover"
        / "sharp_rl_v1"
    )

    sys.path.insert(
        0,
        str(bundle),
    )

    from run_policy import SharpPolicy

    return SharpPolicy(
        bundle
        / "sharp_policy.npz"
    )


def plain_grid_households(
    release,
):
    """
    Target cohort:
    plain-grid households without solar/inverter.
    """

    try:

        from evaluate_sharp_policy_v1 import (
            plain_grid_households as cohort,
        )

        return set(
            cohort(ROOT)
        )

    except Exception:

        return set()


# ============================================================
# RL FEATURE CONSTANTS
# ============================================================

N_BRANCHES = 28

GLOBAL_FEATURES = 25

DEVICE_FEATURES = 10

# Global observation offset:
# obs_grid_peak_severity
SEVERITY = 5

# Per-device observation offsets.
REMAINING_HOURS = 0
POWER_PROXY_KW = 1
PREFERRED_SERVICE = 6


# ============================================================
# ACTION LEVELS
# ============================================================

LEVEL_SHED = 0
LEVEL_ON = 1


# ============================================================
# PHYSICAL SHARP RIG
# ============================================================

RIG = [

    (
        "ceiling_fan_01",
        "ceiling_fan",
        "Ceiling Fan",
        True,
        60.0,
    ),

    (
        "table_fan_01",
        "table_fan",
        "Table Fan",
        True,
        40.0,
    ),

    (
        "led_bulb_01",
        "led_bulb",
        "LED Bulb",
        True,
        9.0,
    ),

    (
        "led_tube_01",
        "led_tube",
        "LED Tube",
        True,
        18.0,
    ),

    (
        "refrigerator_01",
        "refrigerator",
        "Refrigerator",
        True,
        43.2,
    ),

    (
        "air_conditioner_01",
        "air_conditioner",
        "Air Conditioner",
        False,
        1328.4,
    ),

    (
        "washing_machine_01",
        "washing_machine",
        "Washing Machine",
        False,
        113.7,
    ),

    (
        "ev_charger_01",
        "ev_charger",
        "EV Charger",
        False,
        1500.0,
    ),

    (
        "television_01",
        "television",
        "Television",
        False,
        104.6,
    ),

    (
        "mixer_grinder_01",
        "mixer_grinder",
        "Mixer Grinder",
        False,
        500.0,
    ),
]


# ============================================================
# OUTPUT SINKS
# ============================================================

class StdoutSink:
    """Print each MQTT-style message to stdout."""

    def publish(
        self,
        topic,
        payload,
    ):

        print(
            json.dumps({
                "topic": topic,
                "payload": payload,
            }),
            flush=True,
        )

    def close(
        self,
    ):

        pass


class FileSink:
    """Offline fallback sink."""

    def __init__(
        self,
        out: Path,
    ):

        self.out = out

        self.out.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.history = (
            self.out
            / "history.jsonl"
        ).open(
            "w",
            encoding="utf-8",
        )

    def publish(
        self,
        topic,
        payload,
    ):

        name = (
            topic
            .rstrip("/")
            .split("/")[-1]
        )

        (
            self.out
            / f"{name}.json"
        ).write_text(
            json.dumps(
                payload,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.history.write(
            json.dumps({
                "topic": topic,
                "payload": payload,
            })
            + "\n"
        )

        self.history.flush()

    def close(
        self,
    ):

        self.history.close()


class MqttSink:
    """
    HiveMQ MQTT sink.

    State and health are retained so a newly opened dashboard
    immediately receives the latest system state.
    """

    RETAINED = (
        "state",
        "health",
    )

    def __init__(
        self,
        url,
        username=None,
        password=None,
    ):

        try:

            import paho.mqtt.client as mqtt

        except ImportError:

            raise SystemExit(
                "paho-mqtt is missing. Run:\n"
                "pip install paho-mqtt"
            )

        u = urlparse(
            url
        )

        if not u.hostname:

            raise SystemExit(
                f"Invalid MQTT broker URL: {url}"
            )

        transport = (
            "websockets"
            if u.scheme.startswith("ws")
            else "tcp"
        )

        self.client = mqtt.Client(
            callback_api_version=
                mqtt.CallbackAPIVersion.VERSION2,

            transport=transport,

            client_id=(
                "sharp-replay-"
                + str(
                    int(time.time())
                )
            ),
        )

        if username:

            self.client.username_pw_set(
                username,
                password,
            )

        # HiveMQ Cloud TLS.
        if u.scheme in (
            "wss",
            "mqtts",
            "ssl",
        ):

            self.client.tls_set()

        if u.port:

            port = u.port

        elif u.scheme == "wss":

            port = 443

        else:

            port = 8883

        print(
            "🔌 Connecting replay publisher "
            f"to {u.hostname}:{port}",
            file=sys.stderr,
        )

        self.client.connect(
            u.hostname,
            port,
            keepalive=60,
        )

        self.client.loop_start()

        # Allow MQTT network loop to finish connection.
        time.sleep(
            0.5
        )

    def publish(
        self,
        topic,
        payload,
    ):

        retain = (
            topic
            .rstrip("/")
            .split("/")[-1]
            in self.RETAINED
        )

        result = self.client.publish(
            topic,
            json.dumps(
                payload
            ),
            qos=0,
            retain=retain,
        )

        if result.rc != 0:

            print(
                "⚠️ MQTT publish returned "
                f"code {result.rc} "
                f"for {topic}",
                file=sys.stderr,
            )

    def close(
        self,
    ):

        self.client.loop_stop()

        self.client.disconnect()


# ============================================================
# DEVICE CATALOGUE
# ============================================================

def device_catalogue(
    release: Path,
):
    """
    Device slot order MUST match the training generator.

    device_id ascending inside each household.
    """

    devices = pd.read_parquet(
        (
            release
            / "simulator_inputs"
            / "device_power_models.parquet"
        ),
        columns=[
            "template_id",
            "device_id",
            "appliance_type",
            "is_necessity",
            "supports_reduced",
        ],
    )

    devices = devices.sort_values(
        [
            "template_id",
            "device_id",
        ]
    )

    devices[
        "slot"
    ] = (
        devices
        .groupby(
            "template_id"
        )
        .cumcount()
    )

    return devices


# ============================================================
# SERVICE CLASSES
# ============================================================

SERVICE_CLASS = {

    "refrigerator":
        "critical",

    "ceiling_fan":
        "critical",

    "table_fan":
        "critical",

    "led_bulb":
        "critical",

    "led_tube":
        "critical",

    "incandescent_bulb":
        "critical",

    "air_conditioner":
        "thermostatic",

    "air_cooler":
        "thermostatic",

    "washing_machine":
        "deferrable",

    "ev_charger":
        "deferrable",

    "water_heater":
        "deferrable",

    "geyser":
        "deferrable",
}


def service_class(
    appliance_type,
    is_necessity,
):

    if (
        appliance_type
        in SERVICE_CLASS
    ):

        return SERVICE_CLASS[
            appliance_type
        ]

    return (
        "critical"
        if is_necessity
        else "interruptible"
    )


# ============================================================
# BUILD HOME STATE
# ============================================================

def build_state(
    row,
    slots,
    house_id,
    step,
    policy=None,
):

    # --------------------------------------------------------
    # EXACT TRAINED 305-FEATURE OBSERVATION
    # --------------------------------------------------------

    state = np.asarray(
        row.state,
        dtype=float,
    )

    if state.shape != (
        305,
    ):

        raise ValueError(
            "SHARP state must contain exactly "
            f"305 features, got {state.shape}"
        )

    action = np.asarray(
        row.action,
        dtype=int,
    )

    requested = np.asarray(
        row.requested_action,
        dtype=int,
    )

    present = (
        np.asarray(
            row.device_present,
            dtype=float,
        )
        > 0
    )

    severity = float(
        state[
            SEVERITY
        ]
    )

    # --------------------------------------------------------
    # OPTIONAL STANDALONE POLICY
    #
    # Not used during normal integration.
    # rl/mqtt_agent.py will perform the real decision.
    # --------------------------------------------------------

    if policy is not None:

        nec_by_slot = np.zeros(
            N_BRANCHES,
            bool,
        )

        wants_by_slot = np.zeros(
            N_BRANCHES,
            bool,
        )

        for dev in (
            slots.values()
        ):

            slot = dev[
                "slot"
            ]

            if (
                slot is None
                or
                slot >= N_BRANCHES
            ):

                continue

            base = (
                GLOBAL_FEATURES
                + slot
                * DEVICE_FEATURES
            )

            nec_by_slot[
                slot
            ] = bool(
                dev[
                    "is_necessity"
                ]
            )

            wants_by_slot[
                slot
            ] = bool(

                state[
                    base
                    + PREFERRED_SERVICE
                ]
                > 0

                and

                state[
                    base
                    + REMAINING_HOURS
                ]
                > 0
            )

        try:

            action = policy.decide(
                state,

                device_present=
                    present,

                is_necessity=
                    nec_by_slot,

                supports_reduced=
                    np.zeros(
                        N_BRANCHES,
                        bool,
                    ),

                occupant_wants=
                    wants_by_slot,
            )

        except Exception as exc:

            print(
                "policy failed at "
                f"step {step}: {exc}",
                file=sys.stderr,
            )

    # --------------------------------------------------------
    # BUILD PHYSICAL-RIG APPLIANCE STATES
    # --------------------------------------------------------

    appliances = []

    for (
        aid,
        dev,
    ) in slots.items():

        slot = dev[
            "slot"
        ]

        nec = bool(
            dev[
                "is_necessity"
            ]
        )

        # ----------------------------------------------------
        # This rig appliance is not owned by the replayed
        # household.
        # ----------------------------------------------------

        if (
            slot is None

            or

            slot >= len(
                present
            )

            or

            not present[
                slot
            ]
        ):

            appliances.append({

                "appliance_id":
                    aid,

                "display_name":
                    dev[
                        "display_name"
                    ],

                "appliance_type":
                    dev[
                        "appliance_type"
                    ],

                "service_class":
                    service_class(
                        dev[
                            "appliance_type"
                        ],
                        nec,
                    ),

                "is_necessity":
                    nec,

                "supports_reduced":
                    False,

                # IMPORTANT:
                # no trained RL branch maps to
                # this synthetic rig appliance.
                "slot":
                    None,

                "level":
                    LEVEL_SHED,

                "occupant_wants":
                    False,

                "peak_locked_out":
                    False,

                "power_15min_mean_w":
                    0.0,

                # No PZEM.
                "measured_w":
                    None,

                "gpio_state":
                    0,

                "actuation_verified":
                    True,

                "remaining_service_hours":
                    0.0,

                "shed_reason":
                    None,

                "deferred_until":
                    None,

                "no_recorded_demand":
                    True,
            })

            continue

        # ----------------------------------------------------
        # REAL DATASET SLOT
        # ----------------------------------------------------

        base = (
            GLOBAL_FEATURES
            + slot
            * DEVICE_FEATURES
        )

        wants = bool(

            state[
                base
                + PREFERRED_SERVICE
            ]
            > 0

            and

            state[
                base
                + REMAINING_HOURS
            ]
            > 0
        )

        level = (
            int(
                action[
                    slot
                ]
            )
            if slot < len(
                action
            )
            else 0
        )

        asked = (
            int(
                requested[
                    slot
                ]
            )
            if slot < len(
                requested
            )
            else 0
        )

        locked = bool(
            severity >= 0.4
            and
            not nec
            and
            asked > 0
            and
            level == 0
        )

        appliances.append({

            "appliance_id":
                aid,

            "display_name":
                dev[
                    "display_name"
                ],

            "appliance_type":
                dev[
                    "appliance_type"
                ],

            "service_class":
                service_class(
                    dev[
                        "appliance_type"
                    ],
                    nec,
                ),

            "is_necessity":
                nec,

            "supports_reduced":
                False,

            # =================================================
            # CRITICAL:
            # exact BDQ branch used for this device.
            # =================================================

            "slot":
                int(
                    slot
                ),

            "level":
                level,

            "occupant_wants":
                wants,

            "peak_locked_out":
                locked,

            "power_15min_mean_w":
                (
                    dev[
                        "rated_w"
                    ]
                    if level > 0
                    else 0.0
                ),

            # No physical PZEM in current build.
            "measured_w":
                None,

            "gpio_state":
                (
                    1
                    if level > 0
                    else 0
                ),

            "actuation_verified":
                True,

            "remaining_service_hours":
                round(
                    float(
                        state[
                            base
                            + REMAINING_HOURS
                        ]
                    )
                    * 4,
                    2,
                ),

            "shed_reason":
                (
                    "peak_lockout"
                    if locked
                    else None
                ),

            "deferred_until":
                None,
        })

    # --------------------------------------------------------
    # AGGREGATE LOAD
    # --------------------------------------------------------

    background = round(
        float(
            row.background_load_kw
        ),
        4,
    )

    controllable = (
        sum(
            a[
                "power_15min_mean_w"
            ]
            for a in appliances
        )
        / 1000.0
    )

    aggregate = round(
        background
        + controllable,
        4,
    )

    # --------------------------------------------------------
    # MQTT HomeState
    # --------------------------------------------------------

    return {

        "house_id":
            house_id,

        "timestamp_ist":
            str(
                row.timestamp_ist
            ),

        "aggregate_power_kw":
            aggregate,

        "background_load_kw":
            background,

        "sanctioned_load_kw":
            round(
                float(
                    state[8]
                ),
                2,
            ),

        "indoor_temperature_c":
            round(
                float(
                    row.indoor_temperature_c
                ),
                2,
            ),

        "outdoor_temperature_c":
            round(
                float(
                    row.outdoor_temperature_c
                ),
                2,
            ),

        "occupancy_adult_home_fraction":
            round(
                float(
                    row.occupancy_adult_home_fraction
                ),
                3,
            ),

        "attention_available":
            bool(
                row.attention_available
            ),

        "marginal_tariff_inr_kwh":
            round(
                float(
                    row.marginal_tariff_inr_kwh
                ),
                2,
            ),

        "month_to_date_kwh":
            round(
                float(
                    row.month_to_date_kwh
                ),
                2,
            ),

        "grid_peak_severity":
            round(
                severity,
                4,
            ),

        "operating_mode":
            str(
                row.operating_mode
            ),

        "battery_state_of_charge":
            round(
                float(
                    row.battery_kwh
                ),
                3,
            ),

        "grid_absent":
            bool(
                row.grid_absent
            ),

        "appliances":
            appliances,

        # ====================================================
        # CRITICAL:
        # rl/mqtt_agent.py consumes this exact 305-feature
        # raw observation and performs its own normalization.
        # ====================================================

        "state_vector":
            state.tolist(),

        "data_age_seconds":
            0,

        "step_id":
            int(
                step
            ),
    }


# ============================================================
# OPTIONAL REPLAY INTENT
# ============================================================

def build_intent(
    state_message,
    row,
    slots,
):
    """
    Standalone replay intent.

    During normal RL integration this is NOT published because
    rl/mqtt_agent.py publishes the real live model intent.
    """

    requested = np.asarray(
        row.requested_action,
        dtype=int,
    )

    proposed = {}
    executed = {}
    reasons = {}

    for appliance in (
        state_message[
            "appliances"
        ]
    ):

        appliance_id = (
            appliance[
                "appliance_id"
            ]
        )

        executed[
            appliance_id
        ] = appliance[
            "level"
        ]

        proposed[
            appliance_id
        ] = appliance[
            "level"
        ]

        if appliance[
            "peak_locked_out"
        ]:

            proposed[
                appliance_id
            ] = LEVEL_ON

            reasons[
                appliance_id
            ] = [
                "peak_lockout"
            ]

    return {

        "schema_version":
            "sharp_intent_v2",

        "command_id":
            (
                "replay-"
                + str(
                    state_message[
                        "step_id"
                    ]
                )
            ),

        "timestamp_ist":
            state_message[
                "timestamp_ist"
            ],

        "proposed":
            proposed,

        "executed":
            executed,

        "shield_reasons":
            reasons,

        "policy_source":
            "replay:recorded_validation_episode",

        "decision_latency_ms":
            1.2,
    }


# ============================================================
# GRID EVENT
# ============================================================

def build_peak_event(
    state_message,
    sequence,
):

    severity = (
        state_message[
            "grid_peak_severity"
        ]
    )

    active = (
        severity
        >= 0.4
    )

    return {

        "event_id":
            (
                "replay-"
                + state_message[
                    "timestamp_ist"
                ][:10]
                + "-"
                + f"{sequence:03d}"
            ),

        "sequence":
            sequence,

        "region":
            "APCPDCL / Guntur",

        "severity":
            severity,

        "declared_at":
            state_message[
                "timestamp_ist"
            ],

        "expires_at":
            state_message[
                "timestamp_ist"
            ],

        "reason":
            "historical_curve",

        "is_active":
            active,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    parser = (
        argparse.ArgumentParser()
    )

    # --------------------------------------------------------
    # Dataset
    # --------------------------------------------------------

    parser.add_argument(
        "--release",
        type=Path,
        default=(
            ROOT
            / "release"
            / "SHARP_MASTER_V2"
        ),
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    parser.add_argument(
        "--sink",
        choices=[
            "stdout",
            "file",
            "mqtt",
        ],
        default="file",
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=(
            ROOT
            / "dashboard"
            / "public"
            / "feed"
        ),
    )

    # --------------------------------------------------------
    # MQTT
    #
    # Defaults come entirely from root .env.
    # You normally do NOT need to provide these arguments.
    # --------------------------------------------------------

    parser.add_argument(
        "--broker",
        default=
            default_mqtt_broker(),
    )

    parser.add_argument(
        "--username",
        default=
            MQTT_USER,
    )

    parser.add_argument(
        "--password",
        default=
            MQTT_PASS,
    )

    parser.add_argument(
        "--house",
        default=
            HOUSE_ID,
    )

    # --------------------------------------------------------
    # Replay selection
    # --------------------------------------------------------

    parser.add_argument(
        "--episode",
        default=None,
        help=(
            "episode_id; default automatically "
            "selects a useful peak episode"
        ),
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help=(
            "steps per second; "
            "1 = one logical 15-minute "
            "step every real second"
        ),
    )

    parser.add_argument(
        "--start-hour",
        type=int,
        default=11,
        help=(
            "simulated hour to start replay"
        ),
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help=(
            "repeat replay continuously"
        ),
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "publish one state and exit"
        ),
    )

    # --------------------------------------------------------
    # Policy mode
    #
    # IMPORTANT:
    # recorded is default for the current integration because
    # rl/mqtt_agent.py performs LIVE BDQ inference.
    # --------------------------------------------------------

    parser.add_argument(
        "--policy",
        choices=[
            "recorded",
            "sharp",
        ],
        default="recorded",
        help=(
            "'recorded' publishes recorded state "
            "and lets rl/mqtt_agent.py make the live decision. "
            "'sharp' is only for standalone replay."
        ),
    )

    # --------------------------------------------------------
    # Intent publishing
    #
    # Normally FALSE.
    # The real intent comes from rl/mqtt_agent.py.
    # --------------------------------------------------------

    parser.add_argument(
        "--emit-replay-intent",
        action="store_true",
        help=(
            "also publish replay-generated intent; "
            "do not use while live RL MQTT agent is running"
        ),
    )

    args = (
        parser.parse_args()
    )

    # ========================================================
    # MQTT CONFIG VALIDATION
    # ========================================================

    if args.sink == "mqtt":

        missing = []

        if not args.broker:
            missing.append(
                "MQTT_HOST"
            )

        if not args.username:
            missing.append(
                "MQTT_USER"
            )

        if not args.password:
            missing.append(
                "MQTT_PASS"
            )

        if missing:

            raise SystemExit(
                "Missing MQTT configuration "
                "in root .env: "
                + ", ".join(
                    missing
                )
            )

        print(
            "MQTT configuration loaded "
            "from root .env",
            file=sys.stderr,
        )

        print(
            f"  broker: "
            f"{args.broker}",
            file=sys.stderr,
        )

        print(
            f"  user: "
            f"{args.username}",
            file=sys.stderr,
        )

        print(
            "  password loaded: "
            f"{bool(args.password)}",
            file=sys.stderr,
        )

    # ========================================================
    # LOAD VALIDATION TRANSITIONS
    # ========================================================

    validation_path = (
        args.release
        / "rl_transitions"
        / "splits"
        / "validation.parquet"
    )

    if not validation_path.exists():

        raise SystemExit(
            "Validation transitions not found:\n"
            f"{validation_path}"
        )

    frame = (
        pd.read_parquet(
            validation_path
        )
    )

    # Use serve_preferred baseline rows
    # when policy column exists.
    if "policy" in frame:

        frame = frame[
            frame.policy.eq(
                "serve_preferred"
            )
        ]

    # ========================================================
    # SELECT EPISODE
    # ========================================================

    if args.episode:

        frame = frame[
            frame.episode_id.eq(
                args.episode
            )
        ]

        if frame.empty:

            raise SystemExit(
                "No episode found: "
                f"{args.episode}"
            )

    else:

        cohort = (
            plain_grid_households(
                args.release
            )
        )

        devices_all = (
            device_catalogue(
                args.release
            )
        )

        luxury = set(
            devices_all[
                ~devices_all[
                    "is_necessity"
                ].astype(bool)
            ][
                "template_id"
            ]
        )

        best = None
        best_id = None

        for (
            episode,
            group,
        ) in frame.groupby(
            "episode_id"
        ):

            household = (
                group[
                    "household_id"
                ].iloc[0]
            )

            if (
                cohort
                and
                household
                not in cohort
            ):

                continue

            if (
                household
                not in luxury
            ):

                continue

            states = np.stack(
                group[
                    "state"
                ].to_numpy()
            )

            severity = float(
                states[
                    :,
                    SEVERITY
                ].max()
            )

            if severity < 0.4:

                continue

            occupied = float(
                group[
                    "occupancy_adult_home_fraction"
                ].max()
            )

            running = float(
                group[
                    "aggregate_power_kw"
                ].max()
            )

            score = (
                severity
                + occupied
                + min(
                    running,
                    2.0,
                )
            )

            if (
                best is None
                or
                score > best
            ):

                best = score
                best_id = episode

        if best_id is None:

            raise SystemExit(
                "No suitable episode found "
                "with peak + luxury load + occupant."
            )

        frame = frame[
            frame.episode_id.eq(
                best_id
            )
        ]

        states = np.stack(
            frame[
                "state"
            ].to_numpy()
        )

        print(
            (
                f"episode {best_id}\n"
                f"  peak severity   "
                f"{states[:, SEVERITY].max():.2f}\n"
                f"  occupancy       "
                f"{frame.occupancy_adult_home_fraction.max():.2f}\n"
                f"  max draw        "
                f"{frame.aggregate_power_kw.max():.3f} kW"
            ),
            file=sys.stderr,
        )

    frame = (
        frame
        .sort_values(
            "step_id"
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # MAP DATASET DEVICES TO PHYSICAL SHARP RIG
    # ========================================================

    devices = (
        device_catalogue(
            args.release
        )
    )

    household = (
        frame[
            "household_id"
        ].iloc[0]
    )

    mine = (
        devices[
            devices.template_id.eq(
                household
            )
        ]
        .sort_values(
            "slot"
        )
    )

    slots = {}

    taken = set()

    synthetic = []

    for (
        appliance_id,
        appliance_type,
        label,
        necessity,
        watts,
    ) in RIG:

        match = mine[
            mine.appliance_type.eq(
                appliance_type
            )
            &
            ~mine.slot.isin(
                taken
            )
        ]

        entry = {

            "appliance_id":
                appliance_id,

            "display_name":
                label,

            "appliance_type":
                appliance_type,

            "is_necessity":
                necessity,

            "supports_reduced":
                False,

            "rated_w":
                watts,

            "slot":
                None,
        }

        if len(
            match
        ):

            slot = int(
                match.iloc[
                    0
                ].slot
            )

            taken.add(
                slot
            )

            entry[
                "slot"
            ] = slot

        else:

            synthetic.append(
                appliance_id
            )

        slots[
            appliance_id
        ] = entry

    print(
        (
            f"household {household}  "
            f"{len(frame)} steps"
        ),
        file=sys.stderr,
    )

    print(
        (
            "  mapped onto the rig: "
            f"{len(RIG) - len(synthetic)} "
            f"of {len(RIG)} "
            "from recorded data"
        ),
        file=sys.stderr,
    )

    if synthetic:

        print(
            (
                "  idle/not owned: "
                + ", ".join(
                    synthetic
                )
            ),
            file=sys.stderr,
        )

    # ========================================================
    # CREATE SINK
    # ========================================================

    if args.sink == "stdout":

        sink = (
            StdoutSink()
        )

    elif args.sink == "mqtt":

        sink = MqttSink(
            args.broker,
            args.username,
            args.password,
        )

    else:

        sink = FileSink(
            args.out
        )

        print(
            f"writing to "
            f"{args.out}",
            file=sys.stderr,
        )

    # ========================================================
    # OPTIONAL LOCAL POLICY
    # ========================================================

    policy = None

    if args.policy == "sharp":

        policy = (
            load_sharp_policy()
        )

        print(
            "running standalone SHARP "
            "policy inside replay publisher",
            file=sys.stderr,
        )

        if not args.emit_replay_intent:

            print(
                "NOTE: replay intent disabled; "
                "rl/mqtt_agent.py should publish intent",
                file=sys.stderr,
            )

    else:

        print(
            "replaying recorded observations; "
            "live RL decision belongs to "
            "rl/mqtt_agent.py",
            file=sys.stderr,
        )

    # ========================================================
    # REPLAY
    # ========================================================

    start = max(
        0,
        min(
            len(frame) - 1,
            int(
                args.start_hour
                * 4
            ),
        ),
    )

    base = (
        f"home/{args.house}"
    )

    delay = (
        1.0
        / args.speed
        if args.speed > 0
        else 0.0
    )

    sequence = 0

    try:

        while True:

            for index in range(
                start,
                len(frame),
            ):

                row = frame.iloc[
                    index
                ]

                state_message = (
                    build_state(
                        row,
                        slots,
                        args.house,
                        row.step_id,
                        policy,
                    )
                )

                # --------------------------------------------
                # STATE → RL CONTROLLER
                # --------------------------------------------

                sink.publish(
                    f"{base}/state",
                    state_message,
                )

                print(
                    (
                        "📤 STATE "
                        f"step={int(row.step_id)} "
                        f"severity="
                        f"{state_message['grid_peak_severity']:.3f} "
                        "features="
                        f"{len(state_message['state_vector'])}"
                    ),
                    file=sys.stderr,
                )

                # --------------------------------------------
                # OPTIONAL STANDALONE REPLAY INTENT
                #
                # Normally OFF because rl/mqtt_agent.py
                # publishes the real live intent.
                # --------------------------------------------

                if args.emit_replay_intent:

                    sink.publish(
                        f"{base}/intent",
                        build_intent(
                            state_message,
                            row,
                            slots,
                        ),
                    )

                # --------------------------------------------
                # GRID EVENT
                # --------------------------------------------

                sequence += 1

                sink.publish(
                    "grid/guntur/peak_event",
                    build_peak_event(
                        state_message,
                        sequence,
                    ),
                )

                # --------------------------------------------
                # REPLAY HEALTH
                # --------------------------------------------

                sink.publish(
                    f"{base}/health",
                    {
                        "source":
                            "replay_publisher_v1",

                        "published_at":
                            datetime.now()
                            .astimezone()
                            .isoformat(),

                        "step_id":
                            int(
                                row.step_id
                            ),

                        "simulated":
                            True,

                        "state_vector_features":
                            305,

                        "integration_mode":
                            "rl_mqtt_controller",
                    },
                )

                # --------------------------------------------
                # ONE-SHOT MODE
                # --------------------------------------------

                if args.once:

                    return 0

                # --------------------------------------------
                # SPEED CONTROL
                # --------------------------------------------

                if delay:

                    time.sleep(
                        delay
                    )

            if not args.loop:

                return 0

            start = 0

    except KeyboardInterrupt:

        print(
            "\nReplay stopped.",
            file=sys.stderr,
        )

        return 0

    finally:

        sink.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )