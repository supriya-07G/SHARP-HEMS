import os
import json
import ssl
import time
import uuid
import pickle
import threading

from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import deque

import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MQTT_HOST = os.getenv("MQTT_HOST")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
HOUSE_ID = os.getenv("HOUSE_ID", "demo")

RL_ENABLED = os.getenv("RL_ENABLED", "true").lower() in (
    "1", "true", "yes", "on"
)

GPIO_ENABLED = os.getenv("GPIO_ENABLED", "false").lower() in (
    "1", "true", "yes", "on"
)

# This applies ONLY to the USB/table-fan relay on GPIO 23.
# LEDs and L298N are always driven with normal active-high logic.
RELAY_ACTIVE_LOW = os.getenv("RELAY_ACTIVE_LOW", "false").lower() in (
    "1", "true", "yes", "on"
)

OLED_ENABLED = os.getenv("OLED_ENABLED", "true").lower() in (
    "1", "true", "yes", "on"
)
OLED_I2C_PORT = int(os.getenv("OLED_I2C_PORT", "1"))
OLED_I2C_ADDRESS = int(os.getenv("OLED_I2C_ADDRESS", "0x3C"), 0)
OLED_ROTATE_SECONDS = float(os.getenv("OLED_ROTATE_SECONDS", "2.0"))
OLED_COMMAND_SECONDS = float(os.getenv("OLED_COMMAND_SECONDS", "2.0"))

PKL_MODEL_PATH = Path(
    os.getenv(
        "PKL_MODEL_PATH",
        str(ROOT / "models" / "sharp_rl_model.pkl"),
    )
)

MANUAL_OVERRIDE_HOLD_SECONDS = int(
    os.getenv("MANUAL_OVERRIDE_HOLD_SECONDS", "900")
)

# Live weather older than this cannot override RL weather features.
WEATHER_MAX_AGE_SECONDS = int(
    os.getenv("WEATHER_MAX_AGE_SECONDS", "3600")
)

N_BRANCHES = 28
N_LEVELS = 3

LEVEL_NAMES = {
    0: "SHED",
    1: "ON",
    2: "REDUCED",
}


# ============================================================
# MQTT TOPICS
# ============================================================

ACTUATOR_CMD_SUB = f"home/{HOUSE_ID}/actuator/+/cmd"
OVERRIDE_SUB = f"home/{HOUSE_ID}/override/+"
ACTUATOR_ACK_PREFIX = f"home/{HOUSE_ID}/actuator"
HEALTH_TOPIC = f"home/{HOUSE_ID}/health/pi"
STATE_TOPIC = f"home/{HOUSE_ID}/state"
INTENT_TOPIC = f"home/{HOUSE_ID}/intent"
GRID_EVENT_TOPIC = f"home/{HOUSE_ID}/grid/event"
WEATHER_TOPIC = f"home/{HOUSE_ID}/weather"


# ============================================================
# FINAL SHARP HARDWARE REGISTRY — 10 LOGICAL APPLIANCES
# ============================================================
#
# AC is ONE logical appliance controlling THREE LEDs together.
# USB/table fan uses a relay on GPIO 23.
# Ceiling/motor fan uses an L298N with IN1=20 and IN2=21.
#
# Protected/necessity loads match the dashboard contract:
#   ceiling fan, table fan, LED bulb, LED tube, refrigerator.
#
# Flexible loads:
#   AC, washing machine, EV charger, television, mixer grinder.

DEVICES = {
    "air_conditioner_01": {
        "pins": (4, 5, 6),
        "driver": "group_led",
        "display_name": "AC",
        "necessity": False,
        "supports_reduced": False,
    },
    "refrigerator_01": {
        "pins": (13,),
        "driver": "led",
        "display_name": "Fridge",
        "necessity": True,
        "supports_reduced": False,
    },
    "washing_machine_01": {
        "pins": (17,),
        "driver": "led",
        "display_name": "Washer",
        "necessity": False,
        "supports_reduced": False,
    },
    "mixer_grinder_01": {
        "pins": (18,),
        "driver": "led",
        "display_name": "Mixer",
        "necessity": False,
        "supports_reduced": False,
    },
    "television_01": {
        "pins": (19,),
        "driver": "led",
        "display_name": "TV",
        "necessity": False,
        "supports_reduced": False,
    },
    "ev_charger_01": {
        "pins": (26,),
        "driver": "led",
        "display_name": "EV",
        "necessity": False,
        "supports_reduced": False,
    },
    "led_bulb_01": {
        "pins": (22,),
        "driver": "led",
        "display_name": "Light 1",
        "necessity": True,
        "supports_reduced": False,
    },
    "led_tube_01": {
        "pins": (27,),
        "driver": "led",
        "display_name": "Light 2",
        "necessity": True,
        "supports_reduced": False,
    },
    "table_fan_01": {
        "pins": (23,),
        "driver": "relay",
        "display_name": "USB Fan",
        "necessity": True,
        "supports_reduced": False,
    },
    "ceiling_fan_01": {
        "pins": (20, 21),
        "driver": "l298n",
        "display_name": "MotorFan",
        "necessity": True,
        "supports_reduced": False,
    },
}

# Kept as a dictionary because existing RL code only needs membership checks,
# while logs benefit from seeing the actual physical pin group.
GPIO_PINS = {
    appliance_id: config["pins"]
    for appliance_id, config in DEVICES.items()
}

# OLED uses Raspberry Pi I2C1:
# SDA -> GPIO 2, SCL -> GPIO 3.
OLED_SDA_GPIO = 2
OLED_SCL_GPIO = 3

# BUZZER intentionally disconnected / unused.


# ============================================================
# SHARED STATE
# ============================================================

current_levels = {
    device_id: 0
    for device_id in DEVICES
}

manual_override_until = {}
rl_policy = None
active_grid_event = None
latest_weather = None
latest_weather_received_mono = 0.0
mqtt_online = False

state_lock = threading.RLock()


# ============================================================
# OLED STATE
# ============================================================

OLED = None
OLED_FONT = None
oled_stop_event = threading.Event()
oled_thread = None

oled_command_until = 0.0
oled_command_appliance = None
oled_command_level = 0


# ============================================================
# PKL BDQ POLICY
# ============================================================

class PklSharpPolicy:
    REQUIRED_KEYS = (
        "w", "b", "v", "vb", "a", "ab", "mean", "sd"
    )

    def __init__(self, model_path):
        print(f"🤖 Loading PKL model: {model_path}")

        with open(model_path, "rb") as model_file:
            weights = pickle.load(model_file)

        missing = [
            key for key in self.REQUIRED_KEYS
            if key not in weights
        ]
        if missing:
            raise ValueError(f"PKL model missing arrays: {missing}")

        self.w = np.asarray(weights["w"], dtype=float)
        self.b = np.asarray(weights["b"], dtype=float)
        self.v = np.asarray(weights["v"], dtype=float)
        self.vb = np.asarray(weights["vb"], dtype=float)
        self.a = np.asarray(weights["a"], dtype=float)
        self.ab = np.asarray(weights["ab"], dtype=float)
        self.mean = np.asarray(weights["mean"], dtype=float)
        self.sd = np.asarray(weights["sd"], dtype=float)

        if self.w.ndim != 2:
            raise ValueError("PKL w must be a matrix")
        if self.w.shape[0] != 305:
            raise ValueError(
                f"Expected 305 model inputs, got {self.w.shape[0]}"
            )
        if self.a.ndim != 2:
            raise ValueError("PKL advantage head must be a matrix")
        if self.a.shape[1] != N_BRANCHES * N_LEVELS:
            raise ValueError(
                "Expected 84 BDQ outputs (28 x 3), got "
                f"{self.a.shape[1]}"
            )
        if self.mean.shape != (305,):
            raise ValueError("Normalization mean must contain 305 values")
        if self.sd.shape != (305,):
            raise ValueError("Normalization std must contain 305 values")
        if not np.all(np.isfinite(self.mean)):
            raise ValueError("Model mean contains non-finite values")
        if not np.all(np.isfinite(self.sd)):
            raise ValueError("Model std contains non-finite values")
        if np.any(self.sd <= 0):
            raise ValueError("Model std contains zero/negative values")

        print("✅ PKL BDQ loaded: 305 features -> 28 branches x 3 actions")

    def q_values(self, state):
        state = np.asarray(state, dtype=float)

        if state.shape != (305,):
            raise ValueError(
                f"Expected state shape (305,), got {state.shape}"
            )
        if not np.all(np.isfinite(state)):
            raise ValueError("State vector contains non-finite values")

        x = (state - self.mean) / self.sd
        h = np.maximum(0, x @ self.w + self.b)

        advantage = (h @ self.a + self.ab).reshape(
            N_BRANCHES, N_LEVELS
        )
        value = (h @ self.v + self.vb).reshape(1, 1)

        return value + advantage - advantage.mean(axis=1, keepdims=True)

    def decide(
        self,
        state,
        device_present,
        is_necessity,
        supports_reduced,
        occupant_wants,
    ):
        device_present = np.asarray(device_present, dtype=bool)
        is_necessity = np.asarray(is_necessity, dtype=bool)
        supports_reduced = np.asarray(supports_reduced, dtype=bool)
        occupant_wants = np.asarray(occupant_wants, dtype=bool)

        for name, value in (
            ("device_present", device_present),
            ("is_necessity", is_necessity),
            ("supports_reduced", supports_reduced),
            ("occupant_wants", occupant_wants),
        ):
            if value.shape != (N_BRANCHES,):
                raise ValueError(f"{name} must contain 28 values")

        legal = np.ones((N_BRANCHES, N_LEVELS), dtype=bool)

        # Current physical rig is binary. No reduced-power path exists.
        legal[:, 2] = supports_reduced & ~is_necessity

        # Automatic controller cannot shed an essential load the resident wants.
        legal[:, 0] &= ~(is_necessity & occupant_wants)

        q = self.q_values(state)
        allowed = device_present[:, None] & legal

        no_legal_action = device_present & ~allowed.any(axis=1)
        if np.any(no_legal_action):
            bad_slots = np.where(no_legal_action)[0].tolist()
            raise ValueError(
                f"Present devices have no legal action: {bad_slots}"
            )

        actions = np.zeros(N_BRANCHES, dtype=int)

        if np.any(device_present):
            actions[device_present] = np.argmax(
                np.where(
                    allowed[device_present],
                    q[device_present],
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


def remember_command(command_id):
    if not command_id or command_id in seen_commands:
        return

    seen_commands.add(command_id)
    seen_order.append(command_id)

    while len(seen_order) > MAX_SEEN_COMMANDS:
        old = seen_order.popleft()
        seen_commands.discard(old)


# ============================================================
# TIME
# ============================================================

IST = ZoneInfo("Asia/Kolkata")


def timestamp_ist():
    return datetime.now(IST).isoformat()


def parse_datetime(value):
    if not value or not isinstance(value, str):
        return None

    try:
        value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def command_is_expired(command):
    expires_at = parse_datetime(command.get("expires_at"))
    if expires_at is None:
        return False

    return (
        datetime.now(timezone.utc)
        > expires_at.astimezone(timezone.utc)
    )


# ============================================================
# GRID EVENT
# ============================================================

def handle_grid_event(payload_text):
    global active_grid_event

    try:
        event = json.loads(payload_text)
    except json.JSONDecodeError:
        print("❌ Invalid grid event JSON")
        return

    action = event.get("action")

    if action == "cancel":
        with state_lock:
            active_grid_event = None
        print("🟢 Grid event cancelled")
        return

    if action != "declare":
        print("⏭️ Ignoring unknown grid event action")
        return

    try:
        severity = float(event.get("severity"))
    except (TypeError, ValueError):
        print("⏭️ Invalid grid severity")
        return

    if not 0.0 <= severity <= 1.0:
        print("⏭️ Grid severity outside 0..1")
        return

    with state_lock:
        active_grid_event = event

    print(f"🔴 Grid event active → severity {severity:.2f}")


def effective_grid_severity():
    global active_grid_event

    with state_lock:
        event = active_grid_event

    if not event:
        return None

    expires_at = event.get("expires_at")

    if expires_at:
        try:
            expiry = datetime.fromisoformat(
                str(expires_at).replace("Z", "+00:00")
            )
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            if datetime.now(timezone.utc) >= expiry.astimezone(timezone.utc):
                with state_lock:
                    active_grid_event = None
                print("🟢 Grid event expired")
                return None
        except ValueError:
            pass

    try:
        return float(event.get("severity"))
    except (TypeError, ValueError):
        return None


# ============================================================
# LIVE WEATHER OVERRIDE FOR RL FEATURES 0..3
# ============================================================

def handle_weather(payload_text):
    global latest_weather, latest_weather_received_mono

    try:
        envelope = json.loads(payload_text)
    except json.JSONDecodeError:
        print("❌ Invalid weather JSON")
        return

    weather = envelope.get("weather", envelope)
    if not isinstance(weather, dict):
        print("⏭️ Weather ignored: payload has no weather object")
        return

    try:
        temperature_c = float(weather["outdoor_temperature_c"])
        humidity_pct = float(weather["relative_humidity_pct"])
        solar_wm2 = float(weather["solar_irradiance_wm2"])
        wind_kmh = float(weather["wind_speed_kmh"])
    except (KeyError, TypeError, ValueError):
        print("⏭️ Weather ignored: incomplete/non-numeric fields")
        return

    values = (temperature_c, humidity_pct, solar_wm2, wind_kmh)
    if not all(np.isfinite(value) for value in values):
        print("⏭️ Weather ignored: NaN/Inf")
        return

    if not (-10.0 <= temperature_c <= 60.0):
        print("⏭️ Weather ignored: temperature out of range")
        return
    if not (0.0 <= humidity_pct <= 100.0):
        print("⏭️ Weather ignored: humidity out of range")
        return
    if not (0.0 <= solar_wm2 <= 1400.0):
        print("⏭️ Weather ignored: solar irradiance out of range")
        return
    if not (0.0 <= wind_kmh <= 216.0):
        print("⏭️ Weather ignored: wind speed out of range")
        return

    with state_lock:
        latest_weather = {
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "solar_wm2": solar_wm2,
            "wind_ms": wind_kmh / 3.6,
            "last_updated": weather.get("last_updated"),
            "source": envelope.get("source", "mqtt_weather"),
        }
        latest_weather_received_mono = time.monotonic()

    print(
        "🌤️ Live weather cached → "
        f"{temperature_c:.1f}°C, {humidity_pct:.0f}% RH, "
        f"{solar_wm2:.0f} W/m², {wind_kmh:.1f} km/h"
    )


def effective_weather_features():
    with state_lock:
        weather = dict(latest_weather) if latest_weather else None
        received = latest_weather_received_mono

    if not weather or received <= 0.0:
        return None

    if time.monotonic() - received > WEATHER_MAX_AGE_SECONDS:
        return None

    return (
        weather["temperature_c"],
        weather["humidity_pct"],
        weather["solar_wm2"],
        weather["wind_ms"],
    )


# ============================================================
# GPIO
# ============================================================

GPIO = None


def relay_raw_level(logical_on):
    if RELAY_ACTIVE_LOW:
        return 0 if logical_on else 1
    return 1 if logical_on else 0


def relay_logical_state(raw_state):
    if RELAY_ACTIVE_LOW:
        return 0 if raw_state else 1
    return 1 if raw_state else 0


def setup_gpio():
    global GPIO

    if not GPIO_ENABLED:
        print("⚠️ GPIO MODE: SIMULATED")
        return

    try:
        import RPi.GPIO as gpio_module
        GPIO = gpio_module
    except ImportError as exc:
        raise RuntimeError(
            "GPIO_ENABLED=true but RPi.GPIO is not installed"
        ) from exc

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    # Every pin is configured explicitly so relay polarity never affects LEDs
    # or the L298N inputs.
    configured = set()

    for appliance_id, device in DEVICES.items():
        driver = device["driver"]
        pins = device["pins"]

        for pin in pins:
            if pin in configured:
                continue

            if driver == "relay":
                initial = relay_raw_level(False)
            else:
                initial = GPIO.LOW

            GPIO.setup(pin, GPIO.OUT, initial=initial)
            configured.add(pin)

    print("✅ Raspberry Pi GPIO enabled")
    print(
        "USB Fan relay polarity:",
        "ACTIVE LOW" if RELAY_ACTIVE_LOW else "ACTIVE HIGH",
    )
    print("GPIO_PINS:", GPIO_PINS)
    print("AC logical device → GPIO 4, 5, 6 together")
    print("Motor fan L298N → IN1 GPIO20, IN2 GPIO21")


def cleanup_gpio():
    if GPIO_ENABLED and GPIO is not None:
        GPIO.cleanup()


def apply_gpio(appliance_id, level):
    logical_on = level != 0

    if not GPIO_ENABLED:
        print(
            f"🔧 [SIMULATED GPIO] {appliance_id} → level {level}"
        )
        with state_lock:
            current_levels[appliance_id] = level
        return 1 if logical_on else 0

    device = DEVICES[appliance_id]
    driver = device["driver"]
    pins = device["pins"]

    # --------------------------------------------------------
    # AC: GPIO 4, 5, 6 switch together
    # --------------------------------------------------------
    if driver == "group_led":
        output_level = GPIO.HIGH if logical_on else GPIO.LOW
        for pin in pins:
            GPIO.output(pin, output_level)

        readbacks = [int(GPIO.input(pin)) for pin in pins]
        gpio_state = (
            int(all(readbacks))
            if logical_on
            else int(any(readbacks))
        )

        print(
            f"⚡ AC GPIO {pins} | "
            f"{'ON' if logical_on else 'OFF'} | "
            f"readback={readbacks}"
        )

    # --------------------------------------------------------
    # Normal indicator LED
    # --------------------------------------------------------
    elif driver == "led":
        pin = pins[0]
        GPIO.output(pin, GPIO.HIGH if logical_on else GPIO.LOW)
        gpio_state = int(GPIO.input(pin))

        print(
            f"⚡ GPIO BCM {pin} | {appliance_id} | "
            f"{'ON' if logical_on else 'OFF'} | "
            f"readback={gpio_state}"
        )

    # --------------------------------------------------------
    # USB/table fan relay on GPIO 23
    # --------------------------------------------------------
    elif driver == "relay":
        pin = pins[0]
        GPIO.output(pin, relay_raw_level(logical_on))
        raw_readback = int(GPIO.input(pin))
        gpio_state = relay_logical_state(raw_readback)

        print(
            f"⚡ RELAY BCM {pin} | {appliance_id} | "
            f"{'ON' if logical_on else 'OFF'} | "
            f"readback={gpio_state}"
        )

    # --------------------------------------------------------
    # Motor fan via L298N
    # OFF: IN1 LOW, IN2 LOW
    # ON : IN1 HIGH, IN2 LOW
    # --------------------------------------------------------
    elif driver == "l298n":
        in1, in2 = pins

        if logical_on:
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
        else:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)

        read1 = int(GPIO.input(in1))
        read2 = int(GPIO.input(in2))
        gpio_state = int(read1 == 1 and read2 == 0)

        print(
            f"⚡ L298N IN1={in1}:{read1} IN2={in2}:{read2} | "
            f"{appliance_id} | {'ON' if logical_on else 'OFF'}"
        )

    else:
        raise RuntimeError(f"Unknown GPIO driver: {driver}")

    with state_lock:
        current_levels[appliance_id] = level

    return int(gpio_state)


# ============================================================
# OLED DISPLAY
# ============================================================

def setup_oled():
    global OLED, OLED_FONT

    if not OLED_ENABLED:
        print("⚠️ OLED disabled by OLED_ENABLED=false")
        return

    try:
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306
        from PIL import ImageFont

        serial = i2c(
            port=OLED_I2C_PORT,
            address=OLED_I2C_ADDRESS,
        )
        OLED = ssd1306(serial, width=128, height=64)
        OLED_FONT = ImageFont.load_default()
        OLED.clear()
        print(
            f"✅ SSD1306 OLED enabled at I2C "
            f"0x{OLED_I2C_ADDRESS:02X}"
        )
    except Exception as exc:
        OLED = None
        OLED_FONT = None
        print(f"⚠️ OLED unavailable: {exc}")
        print(
            "   Agent will continue without OLED. "
            "Install luma.oled + Pillow and enable I2C if needed."
        )


def oled_draw_lines(lines):
    if OLED is None:
        return

    try:
        from PIL import Image, ImageDraw

        image = Image.new("1", (OLED.width, OLED.height))
        draw = ImageDraw.Draw(image)

        y = 0
        for line in lines[:7]:
            draw.text((0, y), str(line), font=OLED_FONT, fill=255)
            y += 9

        OLED.display(image)
    except Exception as exc:
        print(f"⚠️ OLED draw failed: {exc}")


def level_text(appliance_id):
    with state_lock:
        level = int(current_levels.get(appliance_id, 0))
    return "ON" if level != 0 else "OFF"


def gpio_label(appliance_id):
    pins = DEVICES[appliance_id]["pins"]
    return "/".join(str(pin) for pin in pins)


def trigger_oled_command(appliance_id, level):
    global oled_command_until, oled_command_appliance, oled_command_level

    if OLED is None:
        return

    with state_lock:
        oled_command_appliance = appliance_id
        oled_command_level = int(level)
        oled_command_until = time.monotonic() + OLED_COMMAND_SECONDS


def oled_normal_page(page):
    with state_lock:
        online = mqtt_online

    severity = effective_grid_severity()
    grid_text = (
        f"Grid: PEAK {severity:.2f}"
        if severity is not None and severity >= 0.4
        else "Grid: NORMAL"
    )

    if page == 0:
        return [
            "SHARP HEMS",
            grid_text,
            f"AC       {level_text('air_conditioner_01')}",
            f"Fridge   {level_text('refrigerator_01')}",
            f"Washer   {level_text('washing_machine_01')}",
            f"Mixer    {level_text('mixer_grinder_01')}",
            f"TV       {level_text('television_01')}",
        ]

    return [
        "SHARP HEMS",
        f"MQTT: {'ONLINE' if online else 'OFFLINE'}",
        f"EV       {level_text('ev_charger_01')}",
        f"Light 1  {level_text('led_bulb_01')}",
        f"Light 2  {level_text('led_tube_01')}",
        f"USB Fan  {level_text('table_fan_01')}",
        f"MotorFan {level_text('ceiling_fan_01')}",
    ]


def oled_peak_page():
    severity = effective_grid_severity()
    protected_count = sum(
        1 for device in DEVICES.values()
        if device["necessity"]
    )

    return [
        "SHARP HEMS",
        "GRID PEAK!",
        f"Severity {severity:.2f}" if severity is not None else "Severity --",
        f"AC       {level_text('air_conditioner_01')}",
        f"EV       {level_text('ev_charger_01')}",
        f"Washer   {level_text('washing_machine_01')}",
        f"Protected: {protected_count}",
    ]


def oled_command_page():
    with state_lock:
        appliance_id = oled_command_appliance
        level = oled_command_level

    if not appliance_id or appliance_id not in DEVICES:
        return ["SHARP HEMS", "COMMAND APPLIED"]

    device = DEVICES[appliance_id]

    return [
        "COMMAND APPLIED",
        "",
        device["display_name"],
        "ON" if level != 0 else "OFF",
        "",
        f"GPIO: {gpio_label(appliance_id)}",
    ]


def oled_loop():
    page = 0
    last_rotation = 0.0

    while not oled_stop_event.is_set():
        now = time.monotonic()

        with state_lock:
            command_active = now < oled_command_until

        if command_active:
            oled_draw_lines(oled_command_page())
            oled_stop_event.wait(0.2)
            continue

        severity = effective_grid_severity()

        if severity is not None and severity >= 0.4:
            oled_draw_lines(oled_peak_page())
            oled_stop_event.wait(0.5)
            continue

        if now - last_rotation >= OLED_ROTATE_SECONDS:
            page = 1 - page
            last_rotation = now

        oled_draw_lines(oled_normal_page(page))
        oled_stop_event.wait(0.5)


def start_oled_thread():
    global oled_thread

    if OLED is None:
        return

    oled_stop_event.clear()
    oled_thread = threading.Thread(
        target=oled_loop,
        name="sharp-oled",
        daemon=True,
    )
    oled_thread.start()


def cleanup_oled():
    oled_stop_event.set()

    if oled_thread is not None and oled_thread.is_alive():
        oled_thread.join(timeout=1.0)

    if OLED is not None:
        try:
            OLED.clear()
        except Exception:
            pass


# ============================================================
# SAFETY VALIDATION
# ============================================================

def validate_command(command):
    appliance_id = command.get("appliance_id")
    level = command.get("level")
    source = command.get("source", "unknown")
    occupant_wants = bool(command.get("occupant_wants", True))

    if appliance_id not in DEVICES:
        return False, "level_not_supported"

    device = DEVICES[appliance_id]

    if level not in (0, 1, 2):
        return False, "level_not_supported"

    if level == 2 and not device["supports_reduced"]:
        return False, "level_not_supported"

    automatic_source = source != "resident_override"

    if (
        automatic_source
        and device["necessity"]
        and occupant_wants
        and level == 0
    ):
        return False, "necessity_mask"

    if (
        automatic_source
        and bool(command.get("peak_locked_out", False))
        and level != 0
    ):
        return False, "peak_lockout"

    if command_is_expired(command):
        return False, "command_expired"

    return True, None


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
        "schema_version": "sharp_ack_v2",
        "command_id": command_id,
        "appliance_id": appliance_id,
        "accepted": bool(accepted),
        "applied_level": int(applied_level),
        "rejected_reason": rejected_reason,
        "gpio_state": int(gpio_state),
        "measured_w": None,
        "verification": "NO_METER",
        "acked_at": timestamp_ist(),
        "latency_ms": round(latency_ms, 3),
    }

    topic = f"{ACTUATOR_ACK_PREFIX}/{appliance_id}/ack"

    client.publish(
        topic,
        json.dumps(ack),
        qos=1,
        retain=False,
    )

    print(f"📤 ACK → {topic}")
    print(json.dumps(ack, indent=2))


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(client, payload):
    started = time.perf_counter()

    try:
        command = json.loads(payload)
    except json.JSONDecodeError:
        print("❌ Invalid command JSON")
        return

    command_id = command.get("command_id")
    appliance_id = command.get("appliance_id")
    level = command.get("level")

    if not command_id:
        command_id = "anonymous-" + str(time.time_ns())

    print()
    print("📥 ACTUATOR COMMAND")
    print(json.dumps(command, indent=2))

    if command_id in seen_commands:
        print(f"↩️ Duplicate command ignored: {command_id}")
        return

    remember_command(command_id)

    valid, reason = validate_command(command)

    if not valid:
        latency_ms = (time.perf_counter() - started) * 1000

        with state_lock:
            old_level = current_levels.get(appliance_id, 0)

        publish_ack(
            client=client,
            command_id=command_id,
            appliance_id=appliance_id,
            accepted=False,
            applied_level=old_level,
            rejected_reason=reason,
            gpio_state=1 if old_level != 0 else 0,
            latency_ms=latency_ms,
        )

        print(f"🛡️ COMMAND BLOCKED: {reason}")
        return

    gpio_state = apply_gpio(appliance_id, level)
    # Briefly show the physical command on the OLED before returning
    # to the rotating status screens.
    trigger_oled_command(appliance_id, level)

    latency_ms = (time.perf_counter() - started) * 1000

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

def handle_override(client, payload):
    try:
        override = json.loads(payload)
    except json.JSONDecodeError:
        print("❌ Invalid override JSON")
        return

    print()
    print("👤 RESIDENT OVERRIDE")
    print(json.dumps(override, indent=2))

    appliance_id = override.get("appliance_id")
    requested_level = override.get("requested_level")

    if appliance_id in DEVICES and requested_level in (0, 1):
        with state_lock:
            manual_override_until[appliance_id] = (
                time.monotonic() + MANUAL_OVERRIDE_HOLD_SECONDS
            )

        print(
            f"🧑 Manual authority hold → {appliance_id} for "
            f"{MANUAL_OVERRIDE_HOLD_SECONDS}s"
        )

    command = {
        "schema_version": "sharp_cmd_v2",
        "command_id": override.get(
            "override_id",
            "override-" + str(time.time_ns()),
        ),
        "appliance_id": appliance_id,
        "level": requested_level,
        "issued_at": override.get("issued_at", timestamp_ist()),
        "expires_at": override.get("expires_at"),
        "source": "resident_override",
    }

    handle_command(client, json.dumps(command))


# ============================================================
# RL STATE HANDLER
# ============================================================

def handle_rl_state(client, payload_text):
    global rl_policy

    if not RL_ENABLED:
        return

    if rl_policy is None:
        print("❌ RL enabled but model is not loaded")
        return

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        print("❌ Invalid HomeState JSON")
        return

    raw_state = payload.get("state_vector")

    if raw_state is None:
        print("⏭️ RL skipped: state_vector missing from HomeState")
        return

    try:
        state = np.asarray(raw_state, dtype=float)
    except (TypeError, ValueError):
        print("⏭️ RL skipped: state_vector is not numeric")
        return

    if state.shape != (305,):
        print(f"⏭️ RL skipped: expected 305 features, got {state.shape}")
        return

    if not np.all(np.isfinite(state)):
        print("⏭️ RL skipped: state_vector contains NaN/Inf")
        return

    weather_features = effective_weather_features()

    if weather_features is not None:
        # Frozen state contract:
        # 0=T2M, 1=RH2M, 2=ALLSKY_SFC_SW_DWN, 3=WS10M.
        state = state.copy()
        state[0:4] = np.asarray(weather_features, dtype=float)
        payload["outdoor_temperature_c"] = float(weather_features[0])

    grid_severity = effective_grid_severity()

    if grid_severity is not None:
        # Feature index 5 is obs_grid_peak_severity in the frozen 305-feature
        # training contract. Everything else remains from the state builder.
        state = state.copy()
        state[5] = grid_severity
        payload["grid_peak_severity"] = grid_severity

    appliances = payload.get("appliances", [])

    if not isinstance(appliances, list):
        print("⏭️ RL skipped: appliances must be a list")
        return

    device_present = np.zeros(N_BRANCHES, dtype=bool)
    is_necessity = np.zeros(N_BRANCHES, dtype=bool)
    supports_reduced = np.zeros(N_BRANCHES, dtype=bool)
    occupant_wants = np.zeros(N_BRANCHES, dtype=bool)

    slot_to_appliance = {}
    held_appliances = {}
    now_mono = time.monotonic()

    for appliance in appliances:
        appliance_id = appliance.get("appliance_id")

        # Only physical rig appliances may actuate GPIO.
        if appliance_id not in GPIO_PINS:
            continue

        slot = appliance.get("slot")
        if slot is None:
            continue

        try:
            slot = int(slot)
        except (TypeError, ValueError):
            continue

        if slot < 0 or slot >= N_BRANCHES:
            continue

        if slot in slot_to_appliance:
            print(f"⏭️ RL skipped: duplicate slot {slot}")
            return

        with state_lock:
            hold_until = manual_override_until.get(appliance_id, 0.0)

        if hold_until > now_mono:
            held_appliances[appliance_id] = {
                "slot": slot,
                "remaining_s": round(hold_until - now_mono, 1),
            }
            continue

        with state_lock:
            manual_override_until.pop(appliance_id, None)

        slot_to_appliance[slot] = appliance
        device_present[slot] = True
        is_necessity[slot] = bool(DEVICES[appliance_id]["necessity"])
        supports_reduced[slot] = bool(
            DEVICES[appliance_id]["supports_reduced"]
        )
        occupant_wants[slot] = bool(
            appliance.get("occupant_wants", False)
        )

    if not slot_to_appliance:
        if held_appliances:
            print(
                "⏸️ RL state received, but all mapped devices are under "
                "manual hold"
            )
        else:
            print(
                "⏭️ RL skipped: no wired appliances have valid training "
                "slot values"
            )
        return

    started = time.perf_counter()

    try:
        actions, _ = rl_policy.decide(
            state,
            device_present,
            is_necessity,
            supports_reduced,
            occupant_wants,
        )
    except Exception as exc:
        print(f"❌ RL inference failed: {exc}")
        return

    latency_ms = (time.perf_counter() - started) * 1000
    decision_id = str(uuid.uuid4())

    proposed = {}
    executed = {}
    shield_reasons = {}

    for appliance_id, info in held_appliances.items():
        with state_lock:
            executed[appliance_id] = int(
                current_levels.get(appliance_id, 0)
            )
        shield_reasons[appliance_id] = [
            f"manual_override_hold:{info['remaining_s']}s"
        ]

    print()
    print("🤖 PKL RL DECISION")

    for slot in sorted(slot_to_appliance):
        appliance = slot_to_appliance[slot]
        appliance_id = appliance["appliance_id"]
        level = int(actions[slot])
        proposed[appliance_id] = level

        print(
            f"   slot {slot:02d} | {appliance_id:<24} "
            f"→ {LEVEL_NAMES[level]}"
        )

    intent = {
        "schema_version": "sharp_intent_v2",
        "command_id": decision_id,
        "timestamp_ist": payload.get("timestamp_ist"),
        "proposed": proposed,
        "executed": {**executed, **proposed},
        "shield_reasons": shield_reasons,
        "policy_source": "bdq_v2_pkl_edge",
        "decision_latency_ms": round(latency_ms, 3),
    }

    client.publish(
        INTENT_TOPIC,
        json.dumps(intent),
        qos=0,
        retain=False,
    )
    print(f"📤 Intent → {INTENT_TOPIC}")

    for slot in sorted(slot_to_appliance):
        appliance = slot_to_appliance[slot]
        appliance_id = appliance["appliance_id"]
        level = int(actions[slot])

        with state_lock:
            old_level = current_levels.get(appliance_id, 0)

        if old_level == level:
            print(
                f"   ↪ unchanged | {appliance_id} "
                f"already {LEVEL_NAMES[level]}"
            )
            continue

        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=60)

        command = {
            "schema_version": "sharp_cmd_v2",
            "command_id": f"{decision_id}:{appliance_id}",
            "decision_id": decision_id,
            "appliance_id": appliance_id,
            "level": level,
            "occupant_wants": bool(
                appliance.get("occupant_wants", False)
            ),
            "peak_locked_out": bool(
                appliance.get("peak_locked_out", False)
            ),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "source": "sharp_rl_pkl_v2",
            "state_step_id": payload.get("step_id"),
            "state_timestamp_ist": payload.get("timestamp_ist"),
        }

        handle_command(client, json.dumps(command))

    print(f"⚡ PKL inference: {latency_ms:.3f} ms")


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties):
    global mqtt_online

    print(f"🔌 MQTT CONNECT: {reason_code}")

    if reason_code != 0:
        with state_lock:
            mqtt_online = False
        print("❌ MQTT connection failed")
        return

    with state_lock:
        mqtt_online = True

    print("✅ Connected to HiveMQ")

    client.subscribe(ACTUATOR_CMD_SUB, qos=1)
    client.subscribe(OVERRIDE_SUB, qos=1)

    if RL_ENABLED:
        client.subscribe(STATE_TOPIC, qos=0)

    client.subscribe(GRID_EVENT_TOPIC, qos=1)
    client.subscribe(WEATHER_TOPIC, qos=1)

    print(f"📡 Subscribed → {ACTUATOR_CMD_SUB}")
    print(f"📡 Subscribed → {OVERRIDE_SUB}")

    if RL_ENABLED:
        print(f"📡 Subscribed → {STATE_TOPIC}")

    print(f"📡 Subscribed → {GRID_EVENT_TOPIC}")
    print(f"📡 Subscribed → {WEATHER_TOPIC}")

    client.publish(
        HEALTH_TOPIC,
        json.dumps({
            "source": "sharp_pi_agent",
            "status": "online",
            "gpio_enabled": GPIO_ENABLED,
            "oled_enabled": OLED is not None,
            "appliance_count": len(DEVICES),
            "weather_live": effective_weather_features() is not None,
            "timestamp_ist": timestamp_ist(),
        }),
        qos=0,
        retain=True,
    )


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    global mqtt_online

    with state_lock:
        mqtt_online = False

    print(f"🔌 MQTT DISCONNECTED: {reason_code}")


def on_message(client, userdata, msg):
    print()
    print(f"📨 MQTT: {msg.topic}")

    try:
        payload = msg.payload.decode("utf-8")
    except UnicodeDecodeError:
        print("❌ MQTT payload is not UTF-8")
        return

    if msg.topic == GRID_EVENT_TOPIC:
        handle_grid_event(payload)
        return

    if msg.topic == WEATHER_TOPIC:
        handle_weather(payload)
        return

    if RL_ENABLED and msg.topic == STATE_TOPIC:
        handle_rl_state(client, payload)
        return

    if "/override/" in msg.topic:
        handle_override(client, payload)
        return

    if "/actuator/" in msg.topic and msg.topic.endswith("/cmd"):
        handle_command(client, payload)


# ============================================================
# MAIN
# ============================================================

def main():
    global rl_policy

    missing = []

    if not MQTT_HOST:
        missing.append("MQTT_HOST")
    if not MQTT_USER:
        missing.append("MQTT_USER")
    if not MQTT_PASS:
        missing.append("MQTT_PASS")

    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
        )

    if RL_ENABLED:
        if not PKL_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"PKL model not found: {PKL_MODEL_PATH}"
            )
        rl_policy = PklSharpPolicy(PKL_MODEL_PATH)

    setup_gpio()
    setup_oled()
    start_oled_thread()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="sharp-pi-agent-" + HOUSE_ID,
    )

    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.will_set(
        HEALTH_TOPIC,
        payload=json.dumps({
            "source": "sharp_pi_agent",
            "status": "offline",
        }),
        qos=0,
        retain=True,
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print()
    print("=" * 72)
    print("SHARP RASPBERRY PI ACTUATOR AGENT — FINAL 10-DEVICE RIG")
    print("=" * 72)
    print(f"Broker : {MQTT_HOST}:{MQTT_PORT}")
    print(f"House  : {HOUSE_ID}")
    print(f"GPIO   : {'REAL' if GPIO_ENABLED else 'SIMULATED'}")
    print(
        "Relay  : "
        + ("ACTIVE LOW" if RELAY_ACTIVE_LOW else "ACTIVE HIGH")
        + " (GPIO23 only)"
    )
    print(f"OLED   : {'ENABLED' if OLED is not None else 'DISABLED'}")
    print(f"RL PKL : {'ENABLED' if RL_ENABLED else 'DISABLED'}")
    print(f"Weather: {WEATHER_TOPIC} → RL features 0..3")
    print("Devices: 10")
    print("AC     : GPIO 4 + 5 + 6 together")
    print("Fridge : GPIO 13")
    print("Washer : GPIO 17")
    print("Mixer  : GPIO 18")
    print("TV     : GPIO 19")
    print("EV     : GPIO 26")
    print("Light1 : GPIO 22")
    print("Light2 : GPIO 27")
    print("USB Fan: Relay GPIO 23")
    print("Motor  : L298N GPIO 20 + 21")

    if RL_ENABLED:
        print(f"Model  : {PKL_MODEL_PATH}")
        print(f"State  : {STATE_TOPIC}")
        print(
            f"Hold   : {MANUAL_OVERRIDE_HOLD_SECONDS}s "
            "after resident override"
        )

    print("=" * 72)

    try:
        client.connect(
            MQTT_HOST,
            MQTT_PORT,
            keepalive=60,
        )

        print("Waiting for dashboard/RL commands...")
        client.loop_forever()

    except KeyboardInterrupt:
        print()
        print("Stopping Pi agent...")

    finally:
        try:
            client.publish(
                HEALTH_TOPIC,
                json.dumps({
                    "source": "sharp_pi_agent",
                    "status": "offline",
                    "timestamp_ist": timestamp_ist(),
                }),
                qos=0,
                retain=True,
            )
            client.disconnect()
        except Exception:
            pass

        cleanup_oled()
        cleanup_gpio()


if __name__ == "__main__":
    main()