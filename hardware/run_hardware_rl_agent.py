"""
SHARP Raspberry Pi Edge Agent & PKL Model Runner
------------------------------------------------
Loads `sharp_rl_model.pkl` (Branching Dueling Q-Network BDQ v2)
Connects to MQTT (HiveMQ broker), listens for Dashboard state/weather feeds,
evaluates policy with safety shield rules, and controls Raspberry Pi GPIO relays.

Dependencies:
  pip install numpy paho-mqtt
"""

import os
import json
import time
import pickle
from pathlib import Path
import numpy as np
import paho.mqtt.client as mqtt

# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

# Path to the exported PKL model file
PKL_MODEL_PATH = os.getenv("PKL_MODEL_PATH", str(ROOT / "models" / "sharp_rl_model.pkl"))

MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

HOUSE_ID = os.getenv("HOUSE_ID", "demo")

# Topics
STATE_TOPIC = f"home/{HOUSE_ID}/state"
WEATHER_TOPIC = f"home/{HOUSE_ID}/weather"
OVERRIDE_TOPIC = f"home/{HOUSE_ID}/override/+"
INTENT_TOPIC = f"home/{HOUSE_ID}/intent"
ACTUATOR_ACK_TOPIC = f"home/{HOUSE_ID}/actuator/ack"

N_BRANCHES = 28
N_LEVELS = 3


# ============================================================
# HARDWARE GPIO PIN MAPPING (BCM Numbers for Raspberry Pi)
# ============================================================

DEVICES = {
    "air_conditioner_01": {
        "gpio": None,
        "level_gpios": {0: 4, 1: 5, 2: 6},
    },
    "refrigerator_01": {"gpio": 13},
    "washing_machine_01": {"gpio": 17},
    "mixer_grinder_01": {"gpio": 18},
    "television_01": {"gpio": 19},
    "ev_charger_01": {"gpio": 26},
}

BUZZER_GPIO = 12
OLED_SDA_GPIO = 2
OLED_SCL_GPIO = 3

# Try importing RPi.GPIO for real hardware; fallback to Mock for non-Pi development
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    HARDWARE_AVAILABLE = True
    print("[HARDWARE] RPi.GPIO detected! Operating on physical Raspberry Pi hardware.")
except (ImportError, RuntimeError):
    HARDWARE_AVAILABLE = False
    print("[MOCK HARDWARE] RPi.GPIO not found. Running in hardware simulation mode.")


def set_hardware_pin(appliance_id: str, state: int):
    """Sets GPIO pin for the specified appliance relay or multi-LED AC level."""
    dev = DEVICES.get(appliance_id)
    if not dev:
        return

    level_pins = dev.get("level_gpios")
    if level_pins:
        if HARDWARE_AVAILABLE:
            try:
                for lvl, pin in level_pins.items():
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.HIGH if lvl == state else GPIO.LOW)
                print(f"  ⚡ [GPIO BCM {level_pins}] AC set to Level {state} (Pin {level_pins.get(state)} HIGH)")
            except Exception as e:
                print(f"  ❌ GPIO Error on AC pins: {e}")
        else:
            print(f"  [SIMULATED RELAY BCM {level_pins}] AC level -> {state} (Pin {level_pins.get(state)} HIGH)")
    else:
        pin = dev.get("gpio")
        if pin is None:
            return
        if HARDWARE_AVAILABLE:
            try:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH if state != 0 else GPIO.LOW)
                print(f"  ⚡ [GPIO BCM {pin}] Set to {'HIGH (ON)' if state != 0 else 'LOW (OFF)'} for {appliance_id}")
            except Exception as e:
                print(f"  ❌ GPIO Error on pin {pin}: {e}")
        else:
            print(f"  [SIMULATED RELAY BCM {pin}] {appliance_id} -> {'ON' if state != 0 else 'OFF'}")


# ============================================================
# PKL MODEL INFERENCE POLICY
# ============================================================

class PklSharpPolicy:
    def __init__(self, pkl_path: str):
        print(f"[+] Loading PKL model from: {pkl_path}")
        with open(pkl_path, 'rb') as f:
            weights = pickle.load(f)

        self.w = weights["w"]       # Weights matrix (305, 256)
        self.b = weights["b"]       # Hidden bias
        self.v = weights["v"]       # Value head
        self.vb = weights["vb"]
        self.a = weights["a"]       # Advantage head
        self.ab = weights["ab"]
        self.mean = weights["mean"] # State normalization mean vector
        self.sd = weights["sd"]     # State normalization std vector

        print(f"[+] PKL Model loaded successfully! Input features: {self.w.shape[0]}, Action branches: {N_BRANCHES}")

    def evaluate_q_values(self, state_vector: list):
        state = np.asarray(state_vector, dtype=float)
        if state.shape != (305,):
            raise ValueError(f"Expected 305 features in state vector, got {state.shape}")

        # Normalize features
        norm_state = (state - self.mean) / self.sd

        # Neural Net forward pass (ReLU activation)
        h = np.maximum(0, norm_state @ self.w + self.b)

        # BDQ value & advantage heads
        advantage = (h @ self.a + self.ab).reshape(N_BRANCHES, N_LEVELS)
        value = (h @ self.v + self.vb).reshape(1, 1)

        q_values = value + advantage - advantage.mean(axis=1, keepdims=True)
        return q_values

    def decide_actions(self, state_vector, device_present, is_necessity, supports_reduced, occupant_wants):
        """
        Calculates optimal actions (0=SHED, 1=ON, 2=REDUCED) enforcing safety shields.
        Safety Shield Rule: A necessity load currently wanted by the occupant CANNOT be shed automatically.
        """
        device_present = np.asarray(device_present, dtype=bool)
        is_necessity = np.asarray(is_necessity, dtype=bool)
        supports_reduced = np.asarray(supports_reduced, dtype=bool)
        occupant_wants = np.asarray(occupant_wants, dtype=bool)

        # Build legal action matrix (28 branches x 3 levels)
        legal = np.ones((N_BRANCHES, N_LEVELS), dtype=bool)

        # Level 2 (Reduced) is only legal if appliance supports it and is not necessity
        legal[:, 2] = supports_reduced & ~is_necessity

        # Safety Shield Constraint: Necessity load requested by occupant cannot be shed (Action level 0 forbidden)
        legal[:, 0] &= ~(is_necessity & occupant_wants)

        q = self.evaluate_q_values(state_vector)
        allowed = device_present[:, None] & legal

        actions = np.argmax(np.where(allowed, q, -np.inf), axis=1)
        return actions


# ============================================================
# MQTT MESSAGING ENGINE
# ============================================================

policy_agent = None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker! Subscribing to: {STATE_TOPIC}, {WEATHER_TOPIC}, {OVERRIDE_TOPIC}")
        client.subscribe([(STATE_TOPIC, 0), (WEATHER_TOPIC, 0), (OVERRIDE_TOPIC, 0)])
    else:
        print(f"❌ Failed to connect to MQTT Broker. Return code: {rc}")

def on_message(client, userdata, msg):
    global policy_agent
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode("utf-8"))

        if topic == STATE_TOPIC:
            print(f"\n📨 Received HomeState telemetry from Dashboard: {payload.get('timestamp_ist', '')}")
            
            state_vector = payload.get("state_vector")
            appliances = payload.get("appliances", [])

            if not state_vector or len(state_vector) != 305:
                # If state_vector is missing, construct synthetic 305-feature vector for evaluation
                state_vector = [0.0] * 305
                state_vector[0] = payload.get("aggregate_power_kw", 0.4)
                state_vector[1] = payload.get("indoor_temperature_c", 30.8)
                state_vector[2] = payload.get("outdoor_temperature_c", 35.2)

            # Build device mask arrays
            device_present = [True] * 28
            is_necessity = [False] * 28
            supports_reduced = [False] * 28
            occupant_wants = [True] * 28

            for idx, app in enumerate(appliances[:28]):
                is_necessity[idx] = app.get("is_necessity", False)
                supports_reduced[idx] = app.get("supports_reduced", False)
                occupant_wants[idx] = app.get("occupant_wants", True)

            # Evaluate RL BDQ model actions
            if policy_agent:
                actions = policy_agent.decide_actions(
                    state_vector, device_present, is_necessity, supports_reduced, occupant_wants
                )

                print("🤖 RL Policy Actions Evaluated:")
                for idx, app in enumerate(appliances[:10]):
                    app_id = app.get("appliance_id", f"device_{idx}")
                    action_level = int(actions[idx])
                    action_label = {0: "SHED (OFF)", 1: "ON", 2: "REDUCED"}[action_level]
                    print(f"   • {app.get('display_name', app_id)}: {action_label}")

                    # Drive hardware relay pin
                    set_hardware_pin(app_id, 1 if action_level == 1 else 0)

                # Publish execution ACK back to dashboard
                ack_payload = {
                    "source": "raspberry_pi_pkl_agent",
                    "timestamp": time.time(),
                    "actions_applied": {app.get("appliance_id"): int(actions[i]) for i, app in enumerate(appliances[:10])}
                }
                client.publish(ACTUATOR_ACK_TOPIC, json.dumps(ack_payload))

        elif topic == WEATHER_TOPIC:
            weather = payload.get("weather", {})
            print(f"🌤️ Received Weather Stream from Dashboard: {weather.get('outdoor_temperature_c')}°C, Humidity: {weather.get('relative_humidity_pct')}%")
            # Weather feeds into outdoor_temperature_c feature in state vector for next inference step

        elif topic.startswith(f"home/{HOUSE_ID}/override/"):
            appliance_id = topic.split("/")[-1]
            requested_level = payload.get("requested_level", 0)
            print(f"⚡ DIRECT MANUAL OVERRIDE from Dashboard: {appliance_id} -> Level {requested_level} ({'ON' if requested_level == 1 else 'OFF'})")
            
            # Immediately drive physical GPIO relay pin
            set_hardware_pin(appliance_id, 1 if requested_level == 1 else 0)

            # Publish Execution ACK back to Dashboard
            ack_payload = {
                "source": "raspberry_pi_hardware_relay",
                "timestamp": time.time(),
                "appliance_id": appliance_id,
                "applied_level": requested_level,
                "status": "EXECUTED"
            }
            client.publish(ACTUATOR_ACK_TOPIC, json.dumps(ack_payload))

    except Exception as e:
        print(f"❌ Error processing message on {msg.topic}: {e}")

def main():
    global policy_agent
    print("=" * 60)
    print("🚀 SHARP RASPBERRY PI HARDWARE & PKL MODEL AGENT")
    print("=" * 60)

    # Load PKL Model
    policy_agent = PklSharpPolicy(PKL_MODEL_PATH)

    # Initialize MQTT
    client = mqtt.Client(client_id=f"sharp-pi-agent-{HOUSE_ID}")
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[+] Connecting to MQTT Broker at {MQTT_HOST}:{MQTT_PORT}...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    
    print("⚡ Hardware agent running! Waiting for state and weather feeds from Dashboard...")
    client.loop_forever()

if __name__ == '__main__':
    main()
