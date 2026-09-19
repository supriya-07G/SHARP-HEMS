import os
import json
import ssl
import time

from pathlib import Path
from datetime import datetime, timezone
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

    print(
        "📡 Subscribed → "
        f"{ACTUATOR_CMD_SUB}"
    )

    print(
        "📡 Subscribed → "
        f"{OVERRIDE_SUB}"
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