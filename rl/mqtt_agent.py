import os
import json
import time
import uuid
from pathlib import Path

import numpy as np
import paho.mqtt.client as mqtt


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

CHECKPOINT_PATH = ROOT / "models" / "sharp_bdq_v2" / "checkpoint.npz"

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

STATE_TOPIC = "home/demo/state"
INTENT_TOPIC = "home/demo/intent"

N_BRANCHES = 28
N_LEVELS = 3

LEVEL_NAMES = {
    0: "SHED",
    1: "ON",
    2: "REDUCED",
}


# ============================================================
# LOAD EXISTING SHARP BDQ CHECKPOINT
# ============================================================

class SharpPolicy:

    def __init__(self, weights_path):
        print(f"Loading checkpoint: {weights_path}")

        w = np.load(weights_path, allow_pickle=False)

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

        missing = [key for key in required if key not in w.files]

        if missing:
            raise ValueError(
                f"Checkpoint is missing arrays: {missing}"
            )

        self.w = w["w"]
        self.b = w["b"]

        self.v = w["v"]
        self.vb = w["vb"]

        self.a = w["a"]
        self.ab = w["ab"]

        self.mean = w["mean"]
        self.sd = w["sd"]

        if self.w.shape[0] != 305:
            raise ValueError(
                f"Expected 305 input features, got {self.w.shape[0]}"
            )

        if self.a.shape[1] != 84:
            raise ValueError(
                f"Expected 84 outputs (28 x 3), got {self.a.shape[1]}"
            )

        if len(self.mean) != 305 or len(self.sd) != 305:
            raise ValueError(
                "Normalization vectors must contain 305 values"
            )

        if not np.all(np.isfinite(self.mean)):
            raise ValueError("Normalization mean contains invalid values")

        if not np.all(np.isfinite(self.sd)):
            raise ValueError("Normalization std contains invalid values")

        if np.any(self.sd <= 0):
            raise ValueError("Normalization std contains zero/negative values")

        print(
            f"Loaded BDQ: "
            f"{self.w.shape[0]} features -> "
            f"{N_BRANCHES} branches x {N_LEVELS} levels"
        )

    def q_values(self, state):
        """
        state:
            305 raw feature values.
        """

        state = np.asarray(state, dtype=float)

        if state.shape != (305,):
            raise ValueError(
                f"Expected state shape (305,), got {state.shape}"
            )

        # Same normalization used by the supplied policy.
        x = (state - self.mean) / self.sd

        # BDQ forward pass.
        h = np.maximum(
            0,
            x @ self.w + self.b
        )

        advantage = (
            h @ self.a + self.ab
        ).reshape(
            N_BRANCHES,
            N_LEVELS
        )

        value = (
            h @ self.v + self.vb
        ).reshape(1, 1)

        q = (
            value
            + advantage
            - advantage.mean(axis=1, keepdims=True)
        )

        return q

    def decide(
        self,
        state,
        device_present,
        is_necessity,
        supports_reduced,
        occupant_wants,
    ):
        """
        Select one action for each of the 28 branches.

        0 = SHED
        1 = ON
        2 = REDUCED
        """

        device_present = np.asarray(
            device_present,
            dtype=bool
        )

        is_necessity = np.asarray(
            is_necessity,
            dtype=bool
        )

        supports_reduced = np.asarray(
            supports_reduced,
            dtype=bool
        )

        occupant_wants = np.asarray(
            occupant_wants,
            dtype=bool
        )

        for name, value in [
            ("device_present", device_present),
            ("is_necessity", is_necessity),
            ("supports_reduced", supports_reduced),
            ("occupant_wants", occupant_wants),
        ]:
            if value.shape != (28,):
                raise ValueError(
                    f"{name} must contain 28 values, got {value.shape}"
                )

        # ----------------------------------------------------
        # Legality mask
        # ----------------------------------------------------

        legal = np.ones(
            (N_BRANCHES, N_LEVELS),
            dtype=bool
        )

        # Reduced is only legal if the appliance supports it
        # and is not a necessity.
        legal[:, 2] = (
            supports_reduced
            & ~is_necessity
        )

        # A necessity appliance currently wanted by the
        # occupant cannot be shed.
        legal[:, 0] &= ~(
            is_necessity
            & occupant_wants
        )

        q = self.q_values(state)

        allowed = (
            device_present[:, None]
            & legal
        )

        if not allowed.any(axis=1).all():
            raise ValueError(
                "At least one present device has no legal action"
            )

        action = np.argmax(
            np.where(
                allowed,
                q,
                -np.inf
            ),
            axis=1
        )

        return action, q


# ============================================================
# MQTT
# ============================================================

policy = None


def on_connect(client, userdata, flags, reason_code, properties=None):

    print(
        f"Connected to HiveMQ. "
        f"reason_code={reason_code}"
    )

    if reason_code != 0:
        print("MQTT connection failed.")
        return

    client.subscribe(
        STATE_TOPIC,
        qos=0
    )

    print(
        f"Subscribed to: {STATE_TOPIC}"
    )


def on_message(client, userdata, msg):

    global policy

    try:

        print()
        print("=" * 60)
        print(f"Received MQTT state: {msg.topic}")

        payload = json.loads(
            msg.payload.decode("utf-8")
        )

        # ----------------------------------------------------
        # Extract 305-feature state vector
        # ----------------------------------------------------

        if "state_vector" not in payload:
            print(
                "State message does not contain "
                "'state_vector'."
            )
            print(
                "Available fields:",
                list(payload.keys())
            )
            return

        state = payload["state_vector"]

        # ----------------------------------------------------
        # Appliance legality information
        # ----------------------------------------------------

        appliances = payload.get(
            "appliances",
            []
        )

        device_present = np.zeros(
            N_BRANCHES,
            dtype=bool
        )

        is_necessity = np.zeros(
            N_BRANCHES,
            dtype=bool
        )

        supports_reduced = np.zeros(
            N_BRANCHES,
            dtype=bool
        )

        occupant_wants = np.zeros(
            N_BRANCHES,
            dtype=bool
        )

        # ----------------------------------------------------
        # Current frozen registry ordering:
        #
        # device slots must be ordered consistently with
        # the trained 305-feature representation.
        #
        # For now we use the slot field if supplied.
        # ----------------------------------------------------

        for index, appliance in enumerate(appliances):

            slot = appliance.get(
                "slot",
                index
            )

            if slot >= N_BRANCHES:
                continue

            device_present[slot] = True

            is_necessity[slot] = bool(
                appliance.get(
                    "is_necessity",
                    False
                )
            )

            supports_reduced[slot] = bool(
                appliance.get(
                    "supports_reduced",
                    False
                )
            )

            occupant_wants[slot] = bool(
                appliance.get(
                    "occupant_wants",
                    False
                )
            )

        # ----------------------------------------------------
        # Run RL inference
        # ----------------------------------------------------

        started = time.perf_counter()

        actions, q = policy.decide(
            state,
            device_present,
            is_necessity,
            supports_reduced,
            occupant_wants,
        )

        latency_ms = (
            time.perf_counter() - started
        ) * 1000

        # ----------------------------------------------------
        # Build proposed action map
        # ----------------------------------------------------

        proposed = {}

        for slot in range(N_BRANCHES):

            if not device_present[slot]:
                continue

            appliance_id = appliances[slot].get(
                "appliance_id",
                f"slot_{slot}"
            )

            proposed[appliance_id] = int(
                actions[slot]
            )

            print(
                f"{appliance_id}: "
                f"{LEVEL_NAMES[int(actions[slot])]}"
            )

        # ----------------------------------------------------
        # Publish intent
        # ----------------------------------------------------

        command_id = str(
            uuid.uuid4()
        )

        intent = {
            "schema_version": "sharp_intent_v2",
            "command_id": command_id,
            "timestamp_ist": payload.get(
                "timestamp_ist"
            ),
            "proposed": proposed,
            "executed": proposed.copy(),
            "shield_reasons": {},
            "policy_source": "bdq_v2",
            "decision_latency_ms": round(
                latency_ms,
                3
            ),
        }

        client.publish(
            INTENT_TOPIC,
            json.dumps(intent),
            qos=0,
            retain=False,
        )

        print(
            f"Published intent → {INTENT_TOPIC}"
        )

        print(
            f"RL inference latency: "
            f"{latency_ms:.3f} ms"
        )

        print("=" * 60)

    except Exception as error:

        print()
        print(
            f"ERROR processing MQTT state: {error}"
        )
        print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    global policy

    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(
            f"Checkpoint not found: {CHECKPOINT_PATH}"
        )

    if not MQTT_HOST:
        raise ValueError(
            "MQTT_HOST environment variable is not set"
        )

    if not MQTT_USER:
        raise ValueError(
            "MQTT_USER environment variable is not set"
        )

    if not MQTT_PASS:
        raise ValueError(
            "MQTT_PASS environment variable is not set"
        )

    # --------------------------------------------------------
    # Load policy
    # --------------------------------------------------------

    policy = SharpPolicy(
        CHECKPOINT_PATH
    )

    # --------------------------------------------------------
    # MQTT client
    # --------------------------------------------------------

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"sharp-rl-{uuid.uuid4()}",
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASS
    )

    # HiveMQ Cloud uses TLS on port 8883.
    client.tls_set()

    client.on_connect = on_connect
    client.on_message = on_message

    print()
    print("SHARP RL MQTT Agent")
    print("-" * 60)
    print(f"Broker : {MQTT_HOST}:{MQTT_PORT}")
    print(f"State  : {STATE_TOPIC}")
    print(f"Intent : {INTENT_TOPIC}")
    print(f"Model  : {CHECKPOINT_PATH}")
    print("-" * 60)

    client.connect(
        MQTT_HOST,
        MQTT_PORT,
        keepalive=60,
    )

    print("Waiting for MQTT state messages...")

    client.loop_forever()


if __name__ == "__main__":
    main()