# SHARP Hardware & RL Model Integration Guide

This guide explains how to deploy the **SHARP Reinforcement Learning (RL) Policy (`sharp_rl_model.pkl`)** on the Raspberry Pi hardware rig and connect it in live sync with the **Next.js Web Dashboard**.

---

## 📌 Final Physical Hardware GPIO Mapping

> **Important**: The system uses `GPIO.setmode(GPIO.BCM)`. Wire your LEDs/Relays using the BCM GPIO numbers below.

| Function / Device | Level / Action | BCM GPIO Pin | Physical Pin | Load Class & Shield Rule |
|---|---|---|---|---|
| **Air Conditioner (AC LED 1)** | Level 0 (SHED) | `GPIO 4` | Pin 7 | Red LED / Shedded State |
| **Air Conditioner (AC LED 2)** | Level 1 (ON) | `GPIO 5` | Pin 29 | Green LED / Full Power |
| **Air Conditioner (AC LED 3)** | Level 2 (REDUCED) | `GPIO 6` | Pin 31 | Amber LED / Reduced Power |
| **Refrigerator** | ON / OFF | `GPIO 13` | Pin 33 | 🛡️ Protected Necessity Load |
| **Washing Machine** | ON / OFF | `GPIO 17` | Pin 11 | Deferrable Load |
| **Mixer Grinder** | ON / OFF | `GPIO 18` | Pin 12 | Interruptible Load |
| **Television** | ON / OFF | `GPIO 19` | Pin 35 | Interruptible Load |
| **EV Charging** | ON / OFF | `GPIO 26` | Pin 37 | Deferrable Load |
| **Buzzer Signal** | Alarm / Alert | `GPIO 12` | Pin 32 | Indicator Signal |
| **OLED SCL/SCK** | Display Clock | `GPIO 3` | Pin 5 | I²C Clock (Hardware I²C) |
| **OLED SDA** | Display Data | `GPIO 2` | Pin 3 | I²C Data (Hardware I²C) |

---

## 📁 Files for Hardware Team on Raspberry Pi

| File Path | Description |
|---|---|
| 🐍 [hardware/pi_agent.py](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/hardware/pi_agent.py) | **Raspberry Pi Hardware Agent**: Drives GPIO LEDs & relays based on dashboard commands and RL intents. |
| 🐍 [hardware/run_hardware_rl_agent.py](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/hardware/run_hardware_rl_agent.py) | **RL Policy Runner**: Runs BDQ RL inference (`sharp_rl_model.pkl`) and drives physical GPIO pins. |
| 📦 [models/sharp_rl_model.pkl](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/models/sharp_rl_model.pkl) | **PKL Model Checkpoint** (305-feature Branching Dueling Q-Network BDQ v2). |
| 📋 [hardware/requirements_pi.txt](file:///c:/Users/SUPRIYA/SHARP_Master_Dataset/hardware/requirements_pi.txt) | Dependencies (`numpy`, `paho-mqtt`, `RPi.GPIO`). |

---

## 🚀 Step-by-Step Testing Instructions on Raspberry Pi

### Step 1: Initial Dry Run (Simulation Mode)
In `.env` (or default environment), ensure simulation mode is active:
```env
GPIO_ENABLED=false
```

Run:
```bash
python hardware/pi_agent.py
```
Check that command logs and ACK messages appear cleanly when toggling switches on the dashboard.

### Step 2: Physical Hardware LED Test
Once command and ACK logs are verified, enable physical GPIO pin driving:
```env
GPIO_ENABLED=true
```

Run:
```bash
python hardware/pi_agent.py
```
Test physical LEDs to confirm:
- AC Level 0 (SHED) lights up **GPIO 4**
- AC Level 1 (ON) lights up **GPIO 5**
- AC Level 2 (REDUCED) lights up **GPIO 6**
- Fridge, Washing Machine, Mixer, TV, EV Charger toggle their respective GPIO LEDs.
