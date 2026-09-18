# SHARP Hardware & RL Model Integration Guide

This guide explains how to deploy the **SHARP Reinforcement Learning (RL) Policy (`sharp_rl_model.pkl`)** on the Raspberry Pi hardware rig and connect it in live sync with the **Next.js Web Dashboard**.

---

## 📁 Artifacts & Files for Hardware Team

| File Path | Description |
|---|---|
| 📦 [models/sharp_rl_model.pkl](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/models/sharp_rl_model.pkl) | **PKL Model Checkpoint** (305-feature Branching Dueling Q-Network BDQ v2). |
| 🐍 [hardware/run_hardware_rl_agent.py](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/hardware/run_hardware_rl_agent.py) | **Raspberry Pi Hardware Agent**: Loads PKL model, connects to HiveMQ MQTT broker, and drives GPIO relay pins. |
| 🛠️ [scripts/export_rl_model_pkl.py](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/scripts/export_rl_model_pkl.py) | Exporter script to convert `.npz` checkpoints to `.pkl`. |

---

## 🔌 Hardware GPIO Relay Pinout Mapping (BCM Numbers)

The prototype hardware agent controls 10 relay channels on the Raspberry Pi:

| # | Appliance | Type | Class | GPIO BCM | Default Relay State | Safety Shield Rule |
|---|---|---|---|---|---|---|
| 1 | Ceiling Fan | `ceiling_fan` | **Critical** | `17` | HIGH (ON) | 🛡️ Protected from auto-shedding |
| 2 | Table Fan | `table_fan` | **Critical** | `27` | HIGH (ON) | 🛡️ Protected from auto-shedding |
| 3 | LED Bulb | `led_bulb` | **Critical** | `22` | HIGH (ON) | 🛡️ Protected from auto-shedding |
| 4 | LED Tube | `led_tube` | **Critical** | `19` | HIGH (ON) | 🛡️ Protected from auto-shedding |
| 5 | Refrigerator | `refrigerator` | **Critical** | `23` | HIGH (ON) | 🛡️ Protected from auto-shedding |
| 6 | Air Conditioner | `air_conditioner` | Thermostatic | `16` | Dynamic | Pauses during Grid Peak |
| 7 | Washing Machine | `washing_machine` | Deferrable | `20` | Dynamic | Pauses during Grid Peak |
| 8 | EV Charger | `ev_charger` | Deferrable | `6` | Dynamic | Pauses during Grid Peak |
| 9 | Television | `television` | Interruptible | `21` | Dynamic | Pauses during Grid Peak |
| 10 | Mixer Grinder | `mixer_grinder` | Interruptible | `26` | Dynamic | Pauses during Grid Peak |

---

## 🚀 How to Run the Hardware Agent on Raspberry Pi

### Step 1: Install Lightweight Dependencies
On the Raspberry Pi terminal, install standard requirements (no PyTorch required):
```bash
pip install numpy paho-mqtt RPi.GPIO
```

### Step 2: Set Environment Variables & Launch
```bash
export MQTT_HOST="broker.hivemq.com"
export MQTT_PORT=1883
export HOUSE_ID="demo"

python hardware/run_hardware_rl_agent.py
```

---

## 📡 Live Pact: Dashboard ↔ Hardware Bi-Directional Flow

```
+--------------------------+                         +-------------------------------+
|    Next.js Dashboard     |                         |   Raspberry Pi Edge Agent     |
|  (Browser / Web Client)  |                         | (run_hardware_rl_agent.py)    |
+--------------------------+                         +-------------------------------+
             |                                                       |
             | ---- 1. Broadcasts Weather (home/demo/weather) ---->  |
             | ---- 2. Broadcasts HomeState (home/demo/state) ---->  |
             | ---- 3. Sends Opt-Out (home/demo/override/*) ----->  |
             |                                                       |
             |                                       4. Loads sharp_rl_model.pkl
             |                                       5. Evaluates BDQ Policy & Safety Shield
             |                                       6. Drives GPIO Pins (HIGH/LOW Relays)
             |                                                       |
             | <--- 7. Publishes Execution ACK (home/demo/actuator) -|
```

1. **Weather Stream**: Dashboard sends live Open-Meteo Guntur weather or simulated heatwave parameters (`outdoor_temp_c`, `humidity`, `solar_irradiance`).
2. **State Sync**: Dashboard sends home state telemetry (`aggregate_power_kw`, `appliances`, `grid_peak_severity`).
3. **RL Inference**: The Raspberry Pi evaluates `sharp_rl_model.pkl` with the 305-feature vector and applies the **Safety Shield Layer**:
   - *Safety Shield Rule*: If `is_necessity = True` and `occupant_wants = True`, the RL policy is legally forbidden from shedding action `0` (OFF).
4. **Relay Actuation**: Pi switches physical GPIO relay pins (`17, 27, 22, 19, 23, 16, 20, 6, 21, 26`).
5. **Dashboard Reflection**: Pi publishes actuation acknowledgements back to `home/demo/actuator/ack`, which instantly updates the dashboard status cards.
