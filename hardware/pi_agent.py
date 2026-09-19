import os
import json
import ssl
import time
import uuid
import pickle

from pathlib import Path

import numpy as np
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import deque

import paho.mqtt.client as mqtt

from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(
    __file__
).resolve().parents[1]

load_dotenv(
    ROOT / ".env"
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

RL_ENABLED = (
    os.getenv(
        "RL_ENABLED",
        "true",
    ).lower()
    in (
        "1",
        "true",
        "yes",
        "on",
    )
)

PKL_MODEL_PATH = Path(
    os.getenv(
        "PKL_MODEL_PATH",
        str(
            ROOT
            / "models"
            / "sharp_rl_model.pkl"
        ),
    )
)

MANUAL_OVERRIDE_HOLD_SECONDS = int(
    os.getenv(
        "MANUAL_OVERRIDE_HOLD_SECONDS",
        "900",
    )
)

N_BRANCHES = 28
N_LEVELS = 3

LEVEL_NAMES = {
    0: "SHED",
    1: "ON",
    2: "REDUCED",
}


# ============================================================
# GPIO MODE
# ============================================================

GPIO_ENABLED = (
    os.getenv(
        "GPIO_ENABLED",
        "false",
    ).lower()
    in (
        "1",
        "true",
        "yes",
        "on",
    )
)

RELAY_ACTIVE_LOW = (
    os.getenv(
        "RELAY_ACTIVE_LOW",
        "false",
    ).lower()
    in (
        "1",
        "true",
        "yes",
        "on",
    )
)


# ============================================================
# MQTT TOPICS
# ============================================================

ACTUATOR_CMD_SUB = (
    f"home/{HOUSE_ID}/"
    "actuator/+/cmd"
)

OVERRIDE_SUB = (
    f"home/{HOUSE_ID}/"
    "override/+"
)

ACTUATOR_ACK_PREFIX = (
    f"home/{HOUSE_ID}/"
    "actuator"
)

HEALTH_TOPIC = (
    f"home/{HOUSE_ID}/"
    "health/pi"
)

STATE_TOPIC = (
    f"home/{HOUSE_ID}/state"
)

INTENT_TOPIC = (
    f"home/{HOUSE_ID}/intent"
)

GRID_EVENT_TOPIC = (
    f"home/{HOUSE_ID}/grid/event"
)


# ============================================================
# FROZEN SHARP HARDWARE REGISTRY
# ============================================================

# Primary GPIO pins: these match the physical prototype and the
# dashboard appliance IDs exactly.  Any ID not listed here will
# be rejected with an ACK reason of "level_not_supported".
GPIO_PINS = {
    "air_conditioner_01": 4,
    "refrigerator_01":    13,
    "washing_machine_01": 17,
    "mixer_grinder_01":   18,
    "television_01":      19,
    "ev_charger_01":      26,
}

# Extra prototype LEDs: two additional AC LED channels wired to
# GPIO 5 and 6.  They are not exposed to the dashboard yet, but
# they are initialised LOW at startup so they don't float.
EXTRA_GPIO_PINS = {
    "air_conditioner_02": 5,
    "air_conditioner_03": 6,
}

DEVICES = {
    "air_conditioner_01": {
        "gpio": 4,
        "necessity": False,
        "supports_reduced": False,
    },

    "refrigerator_01": {
        "gpio": 13,
        "necessity": True,
        "supports_reduced": False,
    },

    "washing_machine_01": {
        "gpio": 17,
        "necessity": False,
        "supports_reduced": False,
    },

    "mixer_grinder_01": {
        "gpio": 18,
        "necessity": False,
        "supports_reduced": False,
    },

    "television_01": {
        "gpio": 19,
        "necessity": False,
        "supports_reduced": False,
    },

    "ev_charger_01": {
        "gpio": 26,
        "necessity": False,
        "supports_reduced": False,
    },

    # Extra prototype LEDs — not dashboard-controlled yet;
    # included so that a mis-routed override is ACKed as
    # rejected rather than causing a KeyError.
    "air_conditioner_02": {
        "gpio": 5,
        "necessity": False,
        "supports_reduced": False,
    },

    "air_conditioner_03": {
        "gpio": 6,
        "necessity": False,
        "supports_reduced": False,
    },
}


# ============================================================
# INDICATORS & DISPLAY HARDWARE
# ============================================================

# BUZZER: currently disconnected — do NOT require it.
# BUZZER_GPIO = 12  (kept as a comment; do not set up this pin)

OLED_SDA_GPIO = 2
OLED_SCL_GPIO = 3


# ============================================================
# STATE
# ============================================================

# Safe startup:
# do not energise anything automatically.

current_levels = {
    device_id: 0
    for device_id in DEVICES
}

# Resident commands temporarily take authority over the RL model.
# The hold prevents a new state message from immediately undoing
# a person's manual dashboard action.
manual_override_until = {}

# Loaded once at startup when RL_ENABLED=true.
rl_policy = None
active_grid_event = None


# ============================================================
# PKL BDQ POLICY
# ============================================================

class PklSharpPolicy:

    REQUIRED_KEYS = (
        "w",
        "b",
        "v",
        "vb",
        "a",
        "ab",
        "mean",
        "sd",
    )

    def __init__(
        self,
        model_path,
    ):

        print(
            "🤖 Loading PKL model: "
            f"{model_path}"
        )

        with open(
            model_path,
            "rb",
        ) as model_file:
            weights = pickle.load(
                model_file
            )

        missing = [
            key
            for key in self.REQUIRED_KEYS
            if key not in weights
        ]

        if missing:
            raise ValueError(
                "PKL model missing arrays: "
                f"{missing}"
            )

        self.w = np.asarray(
            weights["w"],
            dtype=float,
        )
        self.b = np.asarray(
            weights["b"],
            dtype=float,
        )
        self.v = np.asarray(
            weights["v"],
            dtype=float,
        )
        self.vb = np.asarray(
            weights["vb"],
            dtype=float,
        )
        self.a = np.asarray(
            weights["a"],
            dtype=float,
        )
        self.ab = np.asarray(
            weights["ab"],
            dtype=float,
        )
        self.mean = np.asarray(
            weights["mean"],
            dtype=float,
        )
        self.sd = np.asarray(
            weights["sd"],
            dtype=float,
        )

        if self.w.ndim != 2:
            raise ValueError(
                "PKL w must be a matrix"
            )

        if self.w.shape[0] != 305:
            raise ValueError(
                "Expected 305 model inputs, "
                f"got {self.w.shape[0]}"
            )

        if self.a.ndim != 2:
            raise ValueError(
                "PKL advantage head must "
                "be a matrix"
            )

        if self.a.shape[1] != (
            N_BRANCHES
            * N_LEVELS
        ):
            raise ValueError(
                "Expected 84 BDQ outputs "
                "(28 x 3), got "
                f"{self.a.shape[1]}"
            )

        if self.mean.shape != (305,):
            raise ValueError(
                "Normalization mean must "
                "contain 305 values"
            )

        if self.sd.shape != (305,):
            raise ValueError(
                "Normalization std must "
                "contain 305 values"
            )

        if not np.all(
            np.isfinite(
                self.mean
            )
        ):
            raise ValueError(
                "Model mean contains "
                "non-finite values"
            )

        if not np.all(
            np.isfinite(
                self.sd
            )
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
            "✅ PKL BDQ loaded: "
            "305 features -> "
            "28 branches x 3 actions"
        )

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

        if not np.all(
            np.isfinite(
                state
            )
        ):
            raise ValueError(
                "State vector contains "
                "non-finite values"
            )

        x = (
            state
            - self.mean
        ) / self.sd

        h = np.maximum(
            0,
            x @ self.w
            + self.b,
        )

        advantage = (
            h @ self.a
            + self.ab
        ).reshape(
            N_BRANCHES,
            N_LEVELS,
        )

        value = (
            h @ self.v
            + self.vb
        ).reshape(
            1,
            1,
        )

        return (
            value
            + advantage
            - advantage.mean(
                axis=1,
                keepdims=True,
            )
        )

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

        for name, value in (
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
        ):
            if value.shape != (
                N_BRANCHES,
            ):
                raise ValueError(
                    f"{name} must contain "
                    "28 values"
                )

        legal = np.ones(
            (
                N_BRANCHES,
                N_LEVELS,
            ),
            dtype=bool,
        )

        # Current physical rig is binary:
        # no reduced-power relay path exists.
        legal[:, 2] = (
            supports_reduced
            & ~is_necessity
        )

        # Automatic SHARP control cannot
        # shed an essential load that the
        # resident currently wants.
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

        actions = np.zeros(
            N_BRANCHES,
            dtype=int,
        )

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
# DUPLICATE COMMAND PROTECTION
# ============================================================

MAX_SEEN_COMMANDS = 500

seen_commands = set()

seen_order = deque()


def remember_command(
    command_id,
):

    if not command_id:
        return

    if command_id in seen_commands:
        return

    seen_commands.add(
        command_id
    )

    seen_order.append(
        command_id
    )

    while (
        len(seen_order)
        > MAX_SEEN_COMMANDS
    ):
        old = (
            seen_order.popleft()
        )

        seen_commands.discard(
            old
        )


# ============================================================
# TIME
# ============================================================

IST = ZoneInfo(
    "Asia/Kolkata"
)


def timestamp_ist():

    return datetime.now(
        IST
    ).isoformat()


def parse_datetime(
    value,
):

    if not value:
        return None

    if not isinstance(
        value,
        str,
    ):
        return None

    try:
        # Support JavaScript timestamps
        # ending in Z.
        value = value.replace(
            "Z",
            "+00:00",
        )

        dt = (
            datetime.fromisoformat(
                value
            )
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt

    except ValueError:
        return None


def command_is_expired(
    command,
):

    expires_at = parse_datetime(
        command.get(
            "expires_at"
        )
    )

    if expires_at is None:
        return False

    return (
        datetime.now(
            timezone.utc
        )
        >
        expires_at.astimezone(
            timezone.utc
        )
    )


# ============================================================
# GPIO
# ============================================================

GPIO = None


def raw_gpio_level(
    logical_on,
):

    if RELAY_ACTIVE_LOW:
        return (
            0
            if logical_on
            else 1
        )

    return (
        1
        if logical_on
        else 0
    )


def logical_gpio_state(
    raw_state,
):

    if RELAY_ACTIVE_LOW:
        return (
            0
            if raw_state
            else 1
        )

    return (
        1
        if raw_state
        else 0
    )


def setup_gpio():

    global GPIO

    if not GPIO_ENABLED:
        print(
            "⚠️ GPIO MODE: SIMULATED"
        )
        return

    try:
        import RPi.GPIO as gpio_module
        GPIO = gpio_module

    except ImportError as exc:
        raise RuntimeError(
            "GPIO_ENABLED=true but "
            "RPi.GPIO is not installed"
        ) from exc

    GPIO.setwarnings(
        False
    )

    GPIO.setmode(
        GPIO.BCM
    )

    off_level = (
        raw_gpio_level(
            False
        )
    )

    # Primary appliance LED pins
    for device in (
        DEVICES.values()
    ):
        pin = device.get("gpio")
        if pin is not None:
            GPIO.setup(
                pin,
                GPIO.OUT,
                initial=off_level,
            )

    # Extra prototype LED pins (AC_02 / AC_03)
    for pin in EXTRA_GPIO_PINS.values():
        GPIO.setup(
            pin,
            GPIO.OUT,
            initial=off_level,
        )

    # NOTE: Buzzer is physically disconnected; skip its setup.
    # OLED uses I²C and does not need GPIO.setup() here.

    print(
        "✅ Raspberry Pi GPIO enabled"
    )

    print(
        "Relay polarity:",
        (
            "ACTIVE LOW"
            if RELAY_ACTIVE_LOW
            else "ACTIVE HIGH"
        ),
    )

    print(
        "GPIO_PINS:",
        GPIO_PINS,
    )


def cleanup_gpio():

    if (
        GPIO_ENABLED
        and
        GPIO is not None
    ):
        GPIO.cleanup()


# ============================================================
# SAFETY VALIDATION
# ============================================================

def validate_command(
    command,
):

    appliance_id = (
        command.get(
            "appliance_id"
        )
    )

    level = command.get(
        "level"
    )

    source = command.get(
        "source",
        "unknown",
    )

    occupant_wants = bool(
        command.get(
            "occupant_wants",
            True,
        )
    )

    # --------------------------------------------------------
    # Device must exist
    # --------------------------------------------------------

    if (
        appliance_id
        not in DEVICES
    ):
        return (
            False,
            "level_not_supported",
        )

    device = DEVICES[
        appliance_id
    ]

    # --------------------------------------------------------
    # Level contract
    # --------------------------------------------------------

    if level not in (
        0,
        1,
        2,
    ):
        return (
            False,
            "level_not_supported",
        )

    # --------------------------------------------------------
    # Level 2 not supported in current hardware prototype
    # --------------------------------------------------------

    if (
        level == 2
        and
        not device[
            "supports_reduced"
        ]
    ):
        return (
            False,
            "level_not_supported",
        )

    # --------------------------------------------------------
    # Automatic controller protection
    #
    # Resident is allowed to switch their own load OFF.
    # SHARP itself cannot shed a necessity load that is
    # currently wanted.
    # --------------------------------------------------------

    automatic_source = (
        source
        != "resident_override"
    )

    if (
        automatic_source
        and
        device[
            "necessity"
        ]
        and
        occupant_wants
        and
        level == 0
    ):
        return (
            False,
            "necessity_mask",
        )

    # A grid/peak lockout is authoritative for automatic RL
    # control. Resident overrides remain independently handled.
    if (
        automatic_source
        and
        bool(
            command.get(
                "peak_locked_out",
                False,
            )
        )
        and
        level != 0
    ):
        return (
            False,
            "peak_lockout",
        )

    # --------------------------------------------------------
    # Expired commands
    # --------------------------------------------------------

    if command_is_expired(
        command
    ):
        return (
            False,
            "command_expired",
        )

    return (
        True,
        None,
    )


# ============================================================
# GPIO ACTUATION
# ============================================================

def apply_gpio(
    appliance_id,
    level,
):

    logical_on = (
        level != 0
    )

    # --------------------------------------------------------
    # SIMULATION MODE
    # --------------------------------------------------------

    if not GPIO_ENABLED:

        print(
            "🔧 [SIMULATED GPIO] "
            f"{appliance_id} "
            f"→ level {level}"
        )

        current_levels[
            appliance_id
        ] = level

        return (
            1
            if logical_on
            else 0
        )

    # --------------------------------------------------------
    # REAL PI GPIO
    # --------------------------------------------------------

    device = DEVICES[appliance_id]
    level_pins = device.get("level_gpios")

    if level_pins:
        # Multi-LED level control (e.g. AC level 0 -> GPIO 4, level 1 -> GPIO 5, level 2 -> GPIO 6)
        for lvl, pin in level_pins.items():
            is_active = (lvl == level)
            GPIO.output(
                pin,
                raw_gpio_level(is_active)
            )

        active_pin = level_pins.get(level, level_pins[0])
        raw_readback = GPIO.input(active_pin)
        gpio_state = logical_gpio_state(raw_readback)
        current_levels[appliance_id] = level

        print(
            f"⚡ GPIO BCM {level_pins} | {appliance_id} | level={level} (Pin {active_pin} ACTIVE) | readback={gpio_state}"
        )
        return int(gpio_state)

    else:
        pin = device["gpio"]
        GPIO.output(
            pin,
            raw_gpio_level(logical_on),
        )

        # Read output register back.
        raw_readback = GPIO.input(pin)
        gpio_state = logical_gpio_state(raw_readback)
        current_levels[appliance_id] = level

        print(
            f"⚡ GPIO BCM {pin} | "
            f"{appliance_id} | "
            f"level={level} | "
            f"readback={gpio_state}"
        )

        return int(gpio_state)


# ============================================================
# MQTT ACK
# ============================================================

def publish_ack(
    client,
    command_id,
    appliance_id,
    accepted,
    applied_level,
    rejected_reason,
    gpio_state,
    latency_ms,
):

    ack = {
        "schema_version":
            "sharp_ack_v2",

        "command_id":
            command_id,

        "appliance_id":
            appliance_id,

        "accepted":
            bool(
                accepted
            ),

        "applied_level":
            int(
                applied_level
            ),

        "rejected_reason":
            rejected_reason,

        "gpio_state":
            int(
                gpio_state
            ),

        # No physical power meter in
        # the current prototype.
        "measured_w":
            None,

        "verification":
            "NO_METER",

        "acked_at":
            timestamp_ist(),

        "latency_ms":
            round(
                latency_ms,
                3,
            ),
    }

    topic = (
        f"{ACTUATOR_ACK_PREFIX}/"
        f"{appliance_id}/ack"
    )

    client.publish(
        topic,
        json.dumps(
            ack
        ),
        qos=1,
        retain=False,
    )

    print(
        f"📤 ACK → {topic}"
    )

    print(
        json.dumps(
            ack,
            indent=2,
        )
    )


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(
    client,
    payload,
):

    started = (
        time.perf_counter()
    )

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:
        command = json.loads(
            payload
        )

    except json.JSONDecodeError:
        print(
            "❌ Invalid command JSON"
        )
        return

    command_id = command.get(
        "command_id"
    )

    appliance_id = command.get(
        "appliance_id"
    )

    level = command.get(
        "level"
    )

    if not command_id:
        command_id = (
            "anonymous-"
            + str(
                time.time_ns()
            )
        )

    print()
    print(
        "📥 ACTUATOR COMMAND"
    )

    print(
        json.dumps(
            command,
            indent=2,
        )
    )

    # --------------------------------------------------------
    # Deduplicate QoS 1 messages
    # --------------------------------------------------------

    if (
        command_id
        in seen_commands
    ):
        print(
            "↩️ Duplicate command ignored: "
            f"{command_id}"
        )
        return

    remember_command(
        command_id
    )

    # --------------------------------------------------------
    # Safety validation
    # --------------------------------------------------------

    valid, reason = (
        validate_command(
            command
        )
    )

    if not valid:

        latency_ms = (
            (
                time.perf_counter()
                - started
            )
            * 1000
        )

        old_level = (
            current_levels.get(
                appliance_id,
                0,
            )
        )

        publish_ack(
            client=client,
            command_id=command_id,
            appliance_id=appliance_id,
            accepted=False,
            applied_level=old_level,
            rejected_reason=reason,
            gpio_state=(
                1
                if old_level != 0
                else 0
            ),
            latency_ms=latency_ms,
        )

        print(
            "🛡️ COMMAND BLOCKED: "
            f"{reason}"
        )

        return

    # --------------------------------------------------------
    # Apply hardware
    # --------------------------------------------------------

    gpio_state = (
        apply_gpio(
            appliance_id,
            level,
        )
    )

    latency_ms = (
        (
            time.perf_counter()
            - started
        )
        * 1000
    )

    # --------------------------------------------------------
    # ACK
    # --------------------------------------------------------

    publish_ack(
        client=client,
        command_id=command_id,
        appliance_id=appliance_id,
        accepted=True,
        applied_level=level,
        rejected_reason=None,
        gpio_state=gpio_state,
        latency_ms=latency_ms,
    )


# ============================================================
# RESIDENT OVERRIDE
# ============================================================

def handle_override(
    client,
    payload,
):

    try:
        override = json.loads(
            payload
        )

    except json.JSONDecodeError:
        print(
            "❌ Invalid override JSON"
        )
        return

    print()
    print(
        "👤 RESIDENT OVERRIDE"
    )

    print(
        json.dumps(
            override,
            indent=2,
        )
    )

    appliance_id = override.get(
        "appliance_id"
    )
    requested_level = override.get(
        "requested_level"
    )

    if (
        appliance_id in DEVICES
        and requested_level in (
            0,
            1,
        )
    ):
        manual_override_until[
            appliance_id
        ] = (
            time.monotonic()
            + MANUAL_OVERRIDE_HOLD_SECONDS
        )

        print(
            "🧑 Manual authority hold → "
            f"{appliance_id} for "
            f"{MANUAL_OVERRIDE_HOLD_SECONDS}s"
        )

    command = {
        "schema_version":
            "sharp_cmd_v2",

        "command_id":
            override.get(
                "override_id",
                (
                    "override-"
                    + str(
                        time.time_ns()
                    )
                ),
            ),

        "appliance_id":
            override.get(
                "appliance_id"
            ),

        "level":
            override.get(
                "requested_level"
            ),

        "issued_at":
            override.get(
                "issued_at",
                timestamp_ist(),
            ),

        "expires_at":
            override.get(
                "expires_at"
            ),

        "source":
            "resident_override",
    }

    handle_command(
        client,
        json.dumps(
            command
        ),
    )


# ============================================================
# GRID EVENT HANDLER
# ============================================================

def handle_grid_event(
    payload_text,
):

    global active_grid_event

    try:
        event = json.loads(
            payload_text
        )
    except json.JSONDecodeError:
        print(
            "❌ Invalid grid event JSON"
        )
        return

    action = event.get(
        "action"
    )

    if action == "cancel":
        active_grid_event = None
        print(
            "🟢 Grid event cancelled"
        )
        return

    if action != "declare":
        print(
            "⏭️ Ignoring unknown grid event action"
        )
        return

    try:
        severity = float(
            event.get(
                "severity"
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        print(
            "⏭️ Invalid grid severity"
        )
        return

    if not 0.0 <= severity <= 1.0:
        print(
            "⏭️ Grid severity outside 0..1"
        )
        return

    active_grid_event = event

    print(
        "🔴 Grid event active → "
        f"severity {severity:.2f}"
    )


def effective_grid_severity():

    global active_grid_event

    event = active_grid_event

    if not event:
        return None

    expires_at = event.get(
        "expires_at"
    )

    if expires_at:
        try:
            expiry = datetime.fromisoformat(
                str(
                    expires_at
                ).replace(
                    "Z",
                    "+00:00",
                )
            )

            if expiry.tzinfo is None:
                expiry = expiry.replace(
                    tzinfo=timezone.utc
                )

            if datetime.now(
                timezone.utc
            ) >= expiry.astimezone(
                timezone.utc
            ):
                active_grid_event = None
                print(
                    "🟢 Grid event expired"
                )
                return None

        except ValueError:
            pass

    try:
        return float(
            event.get(
                "severity"
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# RL STATE HANDLER
# ============================================================

def handle_rl_state(
    client,
    payload_text,
):

    global rl_policy

    if not RL_ENABLED:
        return

    if rl_policy is None:
        print(
            "❌ RL enabled but model "
            "is not loaded"
        )
        return

    try:
        payload = json.loads(
            payload_text
        )
    except json.JSONDecodeError:
        print(
            "❌ Invalid HomeState JSON"
        )
        return

    raw_state = payload.get(
        "state_vector"
    )

    # Never fabricate a model input. The PKL was trained on an
    # exact 305-feature contract; zeros/defaults would create a
    # plausible-looking but invalid control decision.
    if raw_state is None:
        print(
            "⏭️ RL skipped: state_vector "
            "missing from HomeState"
        )
        return

    try:
        state = np.asarray(
            raw_state,
            dtype=float,
        )
    except (
        TypeError,
        ValueError,
    ):
        print(
            "⏭️ RL skipped: state_vector "
            "is not numeric"
        )
        return

    if state.shape != (305,):
        print(
            "⏭️ RL skipped: expected "
            "305 features, got "
            f"{state.shape}"
        )
        return

    if not np.all(
        np.isfinite(
            state
        )
    ):
        print(
            "⏭️ RL skipped: state_vector "
            "contains NaN/Inf"
        )
        return

    grid_severity = effective_grid_severity()

    if grid_severity is not None:
        # Only override the trained grid-severity feature. The remaining
        # 304 model inputs still come from the validated state builder.
        state = state.copy()
        state[5] = grid_severity
        payload["grid_peak_severity"] = grid_severity

    appliances = payload.get(
        "appliances",
        []
    )

    if not isinstance(
        appliances,
        list,
    ):
        print(
            "⏭️ RL skipped: appliances "
            "must be a list"
        )
        return

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

    slot_to_appliance = {}
    held_appliances = {}

    now_mono = time.monotonic()

    # Only the physically wired rig devices are eligible for
    # automatic actuation. Other trained branches remain absent.
    for appliance in appliances:

        appliance_id = appliance.get(
            "appliance_id"
        )

        if appliance_id not in GPIO_PINS:
            continue

        slot = appliance.get(
            "slot"
        )

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

        if slot in slot_to_appliance:
            print(
                "⏭️ RL skipped: duplicate "
                f"slot {slot}"
            )
            return

        hold_until = (
            manual_override_until.get(
                appliance_id,
                0.0,
            )
        )

        if hold_until > now_mono:
            held_appliances[
                appliance_id
            ] = {
                "slot": slot,
                "remaining_s":
                    round(
                        hold_until
                        - now_mono,
                        1,
                    ),
            }
            continue

        manual_override_until.pop(
            appliance_id,
            None,
        )

        slot_to_appliance[
            slot
        ] = appliance

        device_present[
            slot
        ] = True

        # Hardware registry is authoritative for physical
        # safety capability; payload supplies resident intent.
        is_necessity[
            slot
        ] = bool(
            DEVICES[
                appliance_id
            ][
                "necessity"
            ]
        )

        supports_reduced[
            slot
        ] = bool(
            DEVICES[
                appliance_id
            ][
                "supports_reduced"
            ]
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
        if held_appliances:
            print(
                "⏸️ RL state received, "
                "but all mapped devices "
                "are under manual hold"
            )
        else:
            print(
                "⏭️ RL skipped: no wired "
                "appliances have valid "
                "training slot values"
            )
        return

    started = time.perf_counter()

    try:
        actions, _ = (
            rl_policy.decide(
                state,
                device_present,
                is_necessity,
                supports_reduced,
                occupant_wants,
            )
        )
    except Exception as exc:
        print(
            "❌ RL inference failed: "
            f"{exc}"
        )
        return

    latency_ms = (
        (
            time.perf_counter()
            - started
        )
        * 1000
    )

    decision_id = str(
        uuid.uuid4()
    )

    proposed = {}
    executed = {}
    shield_reasons = {}

    for appliance_id, info in (
        held_appliances.items()
    ):
        executed[
            appliance_id
        ] = int(
            current_levels.get(
                appliance_id,
                0,
            )
        )
        shield_reasons[
            appliance_id
        ] = [
            (
                "manual_override_hold:"
                f"{info['remaining_s']}s"
            )
        ]

    print()
    print(
        "🤖 PKL RL DECISION"
    )

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
            f"   slot {slot:02d} | "
            f"{appliance_id:<24} "
            f"→ {LEVEL_NAMES[level]}"
        )

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
        "executed":
            {
                **executed,
                **proposed,
            },
        "shield_reasons":
            shield_reasons,
        "policy_source":
            "bdq_v2_pkl_edge",
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

    # Reuse the exact same safety + GPIO + ACK pipeline that
    # already handles dashboard overrides. There is only ONE
    # owner of the physical GPIO pins.
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

        # Avoid needless relay/LED writes if the physical state
        # already matches the model action.
        if (
            current_levels.get(
                appliance_id,
                0,
            )
            == level
        ):
            print(
                "   ↪ unchanged | "
                f"{appliance_id} "
                f"already {LEVEL_NAMES[level]}"
            )
            continue

        issued_at = datetime.now(
            timezone.utc
        )
        expires_at = (
            issued_at
            + timedelta(
                seconds=60
            )
        )

        command = {
            "schema_version":
                "sharp_cmd_v2",
            "command_id":
                (
                    f"{decision_id}:"
                    f"{appliance_id}"
                ),
            "decision_id":
                decision_id,
            "appliance_id":
                appliance_id,
            "level":
                level,
            "occupant_wants":
                bool(
                    appliance.get(
                        "occupant_wants",
                        False,
                    )
                ),
            "peak_locked_out":
                bool(
                    appliance.get(
                        "peak_locked_out",
                        False,
                    )
                ),
            "issued_at":
                issued_at.isoformat(),
            "expires_at":
                expires_at.isoformat(),
            "source":
                "sharp_rl_pkl_v2",
            "state_step_id":
                payload.get(
                    "step_id"
                ),
            "state_timestamp_ist":
                payload.get(
                    "timestamp_ist"
                ),
        }

        handle_command(
            client,
            json.dumps(
                command
            ),
        )

    print(
        "⚡ PKL inference: "
        f"{latency_ms:.3f} ms"
    )


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):

    print(
        "🔌 MQTT CONNECT: "
        f"{reason_code}"
    )

    if reason_code != 0:
        print(
            "❌ MQTT connection failed"
        )
        return

    print(
        "✅ Connected to HiveMQ"
    )

    client.subscribe(
        ACTUATOR_CMD_SUB,
        qos=1,
    )

    client.subscribe(
        OVERRIDE_SUB,
        qos=1,
    )

    if RL_ENABLED:
        client.subscribe(
            STATE_TOPIC,
            qos=0,
        )

    client.subscribe(
        GRID_EVENT_TOPIC,
        qos=1,
    )

    print(
        "📡 Subscribed → "
        f"{ACTUATOR_CMD_SUB}"
    )

    print(
        "📡 Subscribed → "
        f"{OVERRIDE_SUB}"
    )

    if RL_ENABLED:
        print(
            "📡 Subscribed → "
            f"{STATE_TOPIC}"
        )

    print(
        "📡 Subscribed → "
        f"{GRID_EVENT_TOPIC}"
    )

    client.publish(
        HEALTH_TOPIC,
        json.dumps({
            "source":
                "sharp_pi_agent",

            "status":
                "online",

            "gpio_enabled":
                GPIO_ENABLED,

            "timestamp_ist":
                timestamp_ist(),
        }),
        qos=0,
        retain=True,
    )


def on_message(
    client,
    userdata,
    msg,
):

    print()
    print(
        f"📨 MQTT: "
        f"{msg.topic}"
    )

    payload = (
        msg.payload.decode(
            "utf-8"
        )
    )

    if msg.topic == GRID_EVENT_TOPIC:
        handle_grid_event(
            payload
        )
        return

    if (
        RL_ENABLED
        and msg.topic
        == STATE_TOPIC
    ):
        handle_rl_state(
            client,
            payload,
        )
        return

    if (
        "/override/"
        in msg.topic
    ):
        handle_override(
            client,
            payload,
        )

        return

    if (
        "/actuator/"
        in msg.topic
        and
        msg.topic.endswith(
            "/cmd"
        )
    ):
        handle_command(
            client,
            payload,
        )


# ============================================================
# MAIN
# ============================================================

def main():

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
    # PKL RL model
    # --------------------------------------------------------

    global rl_policy

    if RL_ENABLED:
        if not PKL_MODEL_PATH.exists():
            raise FileNotFoundError(
                "PKL model not found: "
                f"{PKL_MODEL_PATH}"
            )

        rl_policy = PklSharpPolicy(
            PKL_MODEL_PATH
        )

    # --------------------------------------------------------
    # Hardware initialization
    # --------------------------------------------------------

    setup_gpio()

    # --------------------------------------------------------
    # MQTT
    # --------------------------------------------------------

    client = mqtt.Client(
        callback_api_version=
            mqtt.CallbackAPIVersion.VERSION2,

        client_id=(
            "sharp-pi-agent-"
            + HOUSE_ID
        ),
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASS,
    )

    client.tls_set(
        cert_reqs=
            ssl.CERT_REQUIRED,
    )

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30,
    )

    client.will_set(
        HEALTH_TOPIC,
        payload=json.dumps({
            "source":
                "sharp_pi_agent",

            "status":
                "offline",
        }),
        qos=0,
        retain=True,
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
        "SHARP RASPBERRY PI "
        "ACTUATOR AGENT"
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
        "GPIO   : "
        + (
            "REAL"
            if GPIO_ENABLED
            else "SIMULATED"
        )
    )

    print(
        "Relay  : "
        + (
            "ACTIVE LOW"
            if RELAY_ACTIVE_LOW
            else "ACTIVE HIGH"
        )
    )

    print(
        "RL PKL : "
        + (
            "ENABLED"
            if RL_ENABLED
            else "DISABLED"
        )
    )

    if RL_ENABLED:
        print(
            "Model  : "
            f"{PKL_MODEL_PATH}"
        )
        print(
            "State  : "
            f"{STATE_TOPIC}"
        )
        print(
            "Hold   : "
            f"{MANUAL_OVERRIDE_HOLD_SECONDS}s "
            "after resident override"
        )

    print(
        "=" * 68
    )

    try:

        client.connect(
            MQTT_HOST,
            MQTT_PORT,
            keepalive=60,
        )

        print(
            "Waiting for dashboard "
            "override commands..."
        )

        client.loop_forever()

    except KeyboardInterrupt:

        print()
        print(
            "Stopping Pi agent..."
        )

    finally:

        try:
            client.publish(
                HEALTH_TOPIC,
                json.dumps({
                    "source":
                        "sharp_pi_agent",

                    "status":
                        "offline",

                    "timestamp_ist":
                        timestamp_ist(),
                }),
                qos=0,
                retain=True,
            )

            client.disconnect()

        except Exception:
            pass

        cleanup_gpio()


if __name__ == "__main__":
    main()