import os
import json
import time
import uuid

from pathlib import Path
from datetime import datetime, timezone, timedelta

import numpy as np
import paho.mqtt.client as mqtt

from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(
    ROOT / ".env"
)

CHECKPOINT_PATH = (
    ROOT
    / "models"
    / "sharp_bdq_v2"
    / "checkpoint.npz"
)

MQTT_HOST = os.getenv(
    "MQTT_HOST"
)

MQTT_PORT = int(
    os.getenv(
        "MQTT_PORT",
        "8883",
    )
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


# ============================================================
# MQTT TOPICS
# ============================================================

STATE_TOPIC = (
    f"home/{HOUSE_ID}/state"
)

INTENT_TOPIC = (
    f"home/{HOUSE_ID}/intent"
)

ACTUATOR_PREFIX = (
    f"home/{HOUSE_ID}/actuator"
)


# ============================================================
# RL CONSTANTS
# ============================================================

N_BRANCHES = 28
N_LEVELS = 3

LEVEL_NAMES = {
    0: "SHED",
    1: "ON",
    2: "REDUCED",
}


# ============================================================
# SHARP BDQ MODEL
# ============================================================

class SharpPolicy:

    def __init__(
        self,
        weights_path,
    ):

        print(
            f"Loading checkpoint: "
            f"{weights_path}"
        )

        w = np.load(
            weights_path,
            allow_pickle=False,
        )

        required = [
            "w",
            "b",
            "v",
            "vb",
            "a",
            "ab",
            "mean",
            "sd",
        ]

        missing = [
            key
            for key in required
            if key not in w.files
        ]

        if missing:
            raise ValueError(
                "Checkpoint missing arrays: "
                f"{missing}"
            )

        self.w = w["w"]
        self.b = w["b"]

        self.v = w["v"]
        self.vb = w["vb"]

        self.a = w["a"]
        self.ab = w["ab"]

        self.mean = w["mean"]
        self.sd = w["sd"]

        # ----------------------------------------------------
        # Model integrity checks
        # ----------------------------------------------------

        if self.w.shape[0] != 305:
            raise ValueError(
                "Expected 305 model inputs, "
                f"got {self.w.shape[0]}"
            )

        if self.a.shape[1] != 84:
            raise ValueError(
                "Expected 84 BDQ outputs "
                "(28 branches x 3 levels), "
                f"got {self.a.shape[1]}"
            )

        if len(self.mean) != 305:
            raise ValueError(
                "Normalization mean must "
                "contain 305 values"
            )

        if len(self.sd) != 305:
            raise ValueError(
                "Normalization std must "
                "contain 305 values"
            )

        if not np.all(
            np.isfinite(self.mean)
        ):
            raise ValueError(
                "Model mean contains "
                "non-finite values"
            )

        if not np.all(
            np.isfinite(self.sd)
        ):
            raise ValueError(
                "Model std contains "
                "non-finite values"
            )

        if np.any(
            self.sd <= 0
        ):
            raise ValueError(
                "Model std contains "
                "zero/negative values"
            )

        print(
            "✅ BDQ loaded: "
            "305 features -> "
            "28 branches x 3 actions"
        )

    # ========================================================
    # Q VALUES
    # ========================================================

    def q_values(
        self,
        state,
    ):

        state = np.asarray(
            state,
            dtype=float,
        )

        if state.shape != (305,):
            raise ValueError(
                "Expected state shape "
                "(305,), got "
                f"{state.shape}"
            )

        # ----------------------------------------------------
        # Exact training normalization
        # ----------------------------------------------------

        x = (
            state
            - self.mean
        ) / self.sd

        # ----------------------------------------------------
        # Hidden layer
        # ----------------------------------------------------

        h = np.maximum(
            0,
            x @ self.w
            + self.b,
        )

        # ----------------------------------------------------
        # Advantage branches
        # ----------------------------------------------------

        advantage = (
            h @ self.a
            + self.ab
        ).reshape(
            N_BRANCHES,
            N_LEVELS,
        )

        # ----------------------------------------------------
        # Shared value head
        # ----------------------------------------------------

        value = (
            h @ self.v
            + self.vb
        ).reshape(
            1,
            1,
        )

        q = (
            value
            + advantage
            - advantage.mean(
                axis=1,
                keepdims=True,
            )
        )

        return q

    # ========================================================
    # DECISION + SAFETY MASK
    # ========================================================

    def decide(
        self,
        state,
        device_present,
        is_necessity,
        supports_reduced,
        occupant_wants,
    ):

        device_present = np.asarray(
            device_present,
            dtype=bool,
        )

        is_necessity = np.asarray(
            is_necessity,
            dtype=bool,
        )

        supports_reduced = np.asarray(
            supports_reduced,
            dtype=bool,
        )

        occupant_wants = np.asarray(
            occupant_wants,
            dtype=bool,
        )

        arrays = [
            (
                "device_present",
                device_present,
            ),
            (
                "is_necessity",
                is_necessity,
            ),
            (
                "supports_reduced",
                supports_reduced,
            ),
            (
                "occupant_wants",
                occupant_wants,
            ),
        ]

        for name, value in arrays:
            if value.shape != (
                N_BRANCHES,
            ):
                raise ValueError(
                    f"{name} must contain "
                    "28 values, got "
                    f"{value.shape}"
                )

        # ----------------------------------------------------
        # Legal action mask
        # ----------------------------------------------------

        legal = np.ones(
            (
                N_BRANCHES,
                N_LEVELS,
            ),
            dtype=bool,
        )

        # REDUCED only where physically supported.
        #
        # Current prototype has no reduced-level relay control.
        legal[:, 2] = (
            supports_reduced
            & ~is_necessity
        )

        # ----------------------------------------------------
        # Critical safety rule
        #
        # An essential appliance being requested by the
        # occupant may not be automatically shed.
        # ----------------------------------------------------

        legal[:, 0] &= ~(
            is_necessity
            & occupant_wants
        )

        q = self.q_values(
            state
        )

        allowed = (
            device_present[:, None]
            & legal
        )

        # ----------------------------------------------------
        # IMPORTANT FIX:
        #
        # Only PRESENT devices must have a legal action.
        # The old code accidentally treated absent model
        # branches as errors.
        # ----------------------------------------------------

        no_legal_action = (
            device_present
            & ~allowed.any(
                axis=1
            )
        )

        if np.any(
            no_legal_action
        ):
            bad_slots = np.where(
                no_legal_action
            )[0].tolist()

            raise ValueError(
                "Present devices have no "
                "legal action: "
                f"{bad_slots}"
            )

        # Default absent branches to SHED.
        actions = np.zeros(
            N_BRANCHES,
            dtype=int,
        )

        # Only perform argmax for actual devices.
        if np.any(
            device_present
        ):
            actions[
                device_present
            ] = np.argmax(
                np.where(
                    allowed[
                        device_present
                    ],
                    q[
                        device_present
                    ],
                    -np.inf,
                ),
                axis=1,
            )

        return actions, q


# ============================================================
# GLOBAL POLICY
# ============================================================

policy = None


# ============================================================
# MQTT CONNECT
# ============================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):

    print(
        f"MQTT connection result: "
        f"{reason_code}"
    )

    if reason_code != 0:
        print(
            "❌ HiveMQ connection failed"
        )
        return

    print(
        "✅ Connected to HiveMQ"
    )

    client.subscribe(
        STATE_TOPIC,
        qos=0,
    )

    print(
        f"📡 Subscribed → "
        f"{STATE_TOPIC}"
    )


# ============================================================
# PUBLISH PHYSICAL COMMAND
# ============================================================

def publish_actuator_command(
    client,
    decision_id,
    appliance,
    level,
    payload,
):

    appliance_id = (
        appliance[
            "appliance_id"
        ]
    )

    issued = datetime.now(
        timezone.utc
    )

    expires = (
        issued
        + timedelta(
            seconds=60
        )
    )

    command_id = (
        f"{decision_id}:"
        f"{appliance_id}"
    )

    command = {
        "schema_version":
            "sharp_cmd_v2",

        "command_id":
            command_id,

        "decision_id":
            decision_id,

        "appliance_id":
            appliance_id,

        "level":
            int(level),

        # Give the Pi the safety context
        # required to independently reject
        # an illegal automatic shed.
        "occupant_wants":
            bool(
                appliance.get(
                    "occupant_wants",
                    False,
                )
            ),

        "issued_at":
            issued.isoformat(),

        "expires_at":
            expires.isoformat(),

        "source":
            "sharp_rl_bdq_v2",

        "state_step_id":
            payload.get(
                "step_id"
            ),

        "state_timestamp_ist":
            payload.get(
                "timestamp_ist"
            ),
    }

    topic = (
        f"{ACTUATOR_PREFIX}/"
        f"{appliance_id}/cmd"
    )

    client.publish(
        topic,
        json.dumps(
            command
        ),
        qos=1,
        retain=False,
    )

    print(
        "📤 COMMAND → "
        f"{appliance_id}: "
        f"{LEVEL_NAMES[int(level)]}"
    )


# ============================================================
# MQTT STATE HANDLER
# ============================================================

def on_message(
    client,
    userdata,
    msg,
):

    global policy

    try:

        print()
        print(
            "=" * 68
        )

        print(
            f"📥 STATE → "
            f"{msg.topic}"
        )

        payload = json.loads(
            msg.payload.decode(
                "utf-8"
            )
        )

        # ----------------------------------------------------
        # STATE VECTOR
        # ----------------------------------------------------

        if (
            "state_vector"
            not in payload
        ):
            print(
                "❌ state_vector missing "
                "from MQTT HomeState"
            )
            return

        state = np.asarray(
            payload[
                "state_vector"
            ],
            dtype=float,
        )

        if state.shape != (
            305,
        ):
            print(
                "❌ Invalid state vector. "
                f"Expected 305, got "
                f"{state.shape}"
            )
            return

        appliances = payload.get(
            "appliances",
            [],
        )

        # ----------------------------------------------------
        # MODEL BRANCH MASKS
        # ----------------------------------------------------

        device_present = np.zeros(
            N_BRANCHES,
            dtype=bool,
        )

        is_necessity = np.zeros(
            N_BRANCHES,
            dtype=bool,
        )

        supports_reduced = np.zeros(
            N_BRANCHES,
            dtype=bool,
        )

        occupant_wants = np.zeros(
            N_BRANCHES,
            dtype=bool,
        )

        # Physical appliance mapped by RL slot.
        slot_to_appliance = {}

        # ----------------------------------------------------
        # BUILD SLOT MAP
        #
        # Do NOT use appliance list position as the trained
        # model branch. The payload now explicitly supplies
        # the correct slot.
        # ----------------------------------------------------

        for appliance in appliances:

            slot = appliance.get(
                "slot"
            )

            # Rig appliance absent from the dataset
            # episode. It cannot safely be mapped to
            # an RL branch.
            if slot is None:
                continue

            try:
                slot = int(
                    slot
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                slot < 0
                or
                slot >= N_BRANCHES
            ):
                continue

            slot_to_appliance[
                slot
            ] = appliance

            device_present[
                slot
            ] = True

            is_necessity[
                slot
            ] = bool(
                appliance.get(
                    "is_necessity",
                    False,
                )
            )

            supports_reduced[
                slot
            ] = bool(
                appliance.get(
                    "supports_reduced",
                    False,
                )
            )

            occupant_wants[
                slot
            ] = bool(
                appliance.get(
                    "occupant_wants",
                    False,
                )
            )

        if not slot_to_appliance:
            print(
                "❌ No appliances have "
                "valid RL slots"
            )
            return

        # ----------------------------------------------------
        # RL INFERENCE
        # ----------------------------------------------------

        started = (
            time.perf_counter()
        )

        actions, q_values = (
            policy.decide(
                state,
                device_present,
                is_necessity,
                supports_reduced,
                occupant_wants,
            )
        )

        latency_ms = (
            (
                time.perf_counter()
                - started
            )
            * 1000
        )

        # ----------------------------------------------------
        # BUILD ACTION MAP
        # ----------------------------------------------------

        proposed = {}

        for slot in sorted(
            slot_to_appliance
        ):

            appliance = (
                slot_to_appliance[
                    slot
                ]
            )

            appliance_id = (
                appliance[
                    "appliance_id"
                ]
            )

            level = int(
                actions[
                    slot
                ]
            )

            proposed[
                appliance_id
            ] = level

            print(
                f"🤖 slot {slot:02d} | "
                f"{appliance_id:<24} "
                f"→ {LEVEL_NAMES[level]}"
            )

        # ----------------------------------------------------
        # DECISION ID
        # ----------------------------------------------------

        decision_id = str(
            uuid.uuid4()
        )

        # ----------------------------------------------------
        # PUBLISH DASHBOARD INTENT
        # ----------------------------------------------------

        intent = {
            "schema_version":
                "sharp_intent_v2",

            "command_id":
                decision_id,

            "timestamp_ist":
                payload.get(
                    "timestamp_ist"
                ),

            "proposed":
                proposed,

            # This is shield-approved intent.
            # Hardware confirmation comes separately
            # through actuator ACK messages.
            "executed":
                proposed.copy(),

            "shield_reasons":
                {},

            "policy_source":
                "bdq_v2",

            "decision_latency_ms":
                round(
                    latency_ms,
                    3,
                ),
        }

        client.publish(
            INTENT_TOPIC,
            json.dumps(
                intent
            ),
            qos=0,
            retain=False,
        )

        print(
            f"📤 Intent → "
            f"{INTENT_TOPIC}"
        )

        # ----------------------------------------------------
        # PUBLISH ACTUATOR COMMANDS
        # ----------------------------------------------------

        for slot in sorted(
            slot_to_appliance
        ):

            appliance = (
                slot_to_appliance[
                    slot
                ]
            )

            level = int(
                actions[
                    slot
                ]
            )

            publish_actuator_command(
                client=client,
                decision_id=decision_id,
                appliance=appliance,
                level=level,
                payload=payload,
            )

        print(
            "⚡ RL inference: "
            f"{latency_ms:.3f} ms"
        )

        print(
            "=" * 68
        )

    except Exception as error:

        print()
        print(
            "❌ ERROR processing "
            "MQTT state:"
        )
        print(
            repr(error)
        )
        print(
            "=" * 68
        )


# ============================================================
# MAIN
# ============================================================

def main():

    global policy

    # --------------------------------------------------------
    # Validate model
    # --------------------------------------------------------

    if not (
        CHECKPOINT_PATH.exists()
    ):
        raise FileNotFoundError(
            "Checkpoint not found: "
            f"{CHECKPOINT_PATH}"
        )

    # --------------------------------------------------------
    # Validate MQTT configuration
    # --------------------------------------------------------

    missing = []

    if not MQTT_HOST:
        missing.append(
            "MQTT_HOST"
        )

    if not MQTT_USER:
        missing.append(
            "MQTT_USER"
        )

    if not MQTT_PASS:
        missing.append(
            "MQTT_PASS"
        )

    if missing:
        raise RuntimeError(
            "Missing environment "
            "variables: "
            + ", ".join(
                missing
            )
        )

    # --------------------------------------------------------
    # Load RL policy
    # --------------------------------------------------------

    policy = SharpPolicy(
        CHECKPOINT_PATH
    )

    # --------------------------------------------------------
    # MQTT client
    # --------------------------------------------------------

    client = mqtt.Client(
        callback_api_version=
            mqtt.CallbackAPIVersion.VERSION2,

        client_id=(
            "sharp-rl-"
            + uuid.uuid4().hex[:8]
        ),
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASS,
    )

    # HiveMQ Cloud TLS
    client.tls_set()

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30,
    )

    client.on_connect = (
        on_connect
    )

    client.on_message = (
        on_message
    )

    print()
    print(
        "=" * 68
    )
    print(
        "SHARP RL MQTT CONTROLLER"
    )
    print(
        "=" * 68
    )

    print(
        f"Broker : "
        f"{MQTT_HOST}:"
        f"{MQTT_PORT}"
    )

    print(
        f"House  : "
        f"{HOUSE_ID}"
    )

    print(
        f"State  : "
        f"{STATE_TOPIC}"
    )

    print(
        f"Intent : "
        f"{INTENT_TOPIC}"
    )

    print(
        "Cmd    : "
        f"{ACTUATOR_PREFIX}/"
        "<appliance>/cmd"
    )

    print(
        f"Model  : "
        f"{CHECKPOINT_PATH}"
    )

    print(
        "=" * 68
    )

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=60,
    )

    print(
        "Waiting for HomeState "
        "messages..."
    )

    client.loop_forever()


if __name__ == "__main__":
    main()