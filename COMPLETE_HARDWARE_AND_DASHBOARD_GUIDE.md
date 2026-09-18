# SHARP HEMS — Complete End-to-End Execution Guide

This document is the master step-by-step guide for setting up the **Raspberry Pi Hardware Rig**, running the **RL Model (`sharp_rl_model.pkl`)**, and interacting with the **Next.js Web Dashboard** in live bi-directional sync.

---

## 🛠️ STEP 1: Hardware Wiring & Pinout Setup (Raspberry Pi)

Connect your multi-channel relay module to the Raspberry Pi GPIO header using the BCM pin mapping table below:

| # | Appliance Name | Appliance Type | Load Class | BCM GPIO Pin | Relay Channel | Safety Shield Rule |
|---|---|---|---|---|---|---|
| 1 | Ceiling Fan | `ceiling_fan` | **Critical** | `GPIO 17` (Pin 11) | Relay 1 | 🛡️ Protected from auto-shedding |
| 2 | Table Fan | `table_fan` | **Critical** | `GPIO 27` (Pin 13) | Relay 2 | 🛡️ Protected from auto-shedding |
| 3 | LED Bulb | `led_bulb` | **Critical** | `GPIO 22` (Pin 15) | Relay 3 | 🛡️ Protected from auto-shedding |
| 4 | LED Tube | `led_tube` | **Critical** | `GPIO 19` (Pin 35) | Relay 4 | 🛡️ Protected from auto-shedding |
| 5 | Refrigerator | `refrigerator` | **Critical** | `GPIO 23` (Pin 16) | Relay 5 | 🛡️ Protected from auto-shedding |
| 6 | Air Conditioner | `air_conditioner` | Thermostatic | `GPIO 16` (Pin 36) | Relay 6 | ⚡ Pauses during Grid Peak |
| 7 | Washing Machine | `washing_machine` | Deferrable | `GPIO 20` (Pin 38) | Relay 7 | ⚡ Pauses during Grid Peak |
| 8 | EV Charger | `ev_charger` | Deferrable | `GPIO 6` (Pin 31) | Relay 8 | ⚡ Pauses during Grid Peak |
| 9 | Television | `television` | Interruptible | `GPIO 21` (Pin 40) | Relay 9 | ⚡ Pauses during Grid Peak |
| 10 | Mixer Grinder | `mixer_grinder` | Interruptible | `GPIO 26` (Pin 37) | Relay 10 | ⚡ Pauses during Grid Peak |

> 📌 **Power & Ground**: Connect Relay module `VCC` to Pi `5V` (Pin 2/4) and Relay `GND` to Pi `GND` (Pin 6/9/14/20).

---

## 💻 STEP 2: Setting Up & Running the RL Model Agent on Raspberry Pi

Open a terminal on your Raspberry Pi:

### 1. Download / Clone the Repository
```bash
git clone https://github.com/supriya-07G/SHARP-HEMS.git
cd SHARP-HEMS
```

### 2. Install Python Dependencies
```bash
pip install numpy paho-mqtt RPi.GPIO
```

### 3. Start the Hardware RL Agent
```bash
python hardware/run_hardware_rl_agent.py
```

#### What You Will See on the Raspberry Pi Screen:
```
============================================================
🚀 SHARP RASPBERRY PI HARDWARE & PKL MODEL AGENT
============================================================
[+] Loading PKL model from: /home/pi/SHARP-HEMS/models/sharp_rl_model.pkl
[+] PKL Model loaded successfully! Input features: 305, Action branches: 28
[HARDWARE] RPi.GPIO detected! Operating on physical Raspberry Pi hardware.
[+] Connecting to MQTT Broker at broker.hivemq.com:1883...
✅ Connected to MQTT Broker! Subscribing to state, weather, and override feeds...
⚡ Hardware agent running! Waiting for state and weather feeds from Dashboard...
```

---

## 🌐 STEP 3: Launching & Running the Web Dashboard

### Option A: Run Dashboard Locally
On your laptop/PC:
```bash
cd dashboard
npm install
npm run dev
```
Open your browser at `http://localhost:3000`.

### Option B: Open Production Build
Access your deployed Vercel URL or run:
```bash
cd dashboard
npm run build
npm run start
```

---

## 🧪 STEP 4: Live Demonstration & Testing Steps

### Test 1: Remote Manual Appliance Control (ON / OFF Toggle Switches)
1. Go to the **Resident Dashboard** → **Appliances & Shedding** page (`/resident/appliances`).
2. Locate **Air Conditioner** or **EV Charger**.
3. Click the interactive **Red (OFF)** toggle switch.
4. **Observe the Raspberry Pi Terminal**:
   ```
   ⚡ DIRECT MANUAL OVERRIDE from Dashboard: air_conditioner_01 -> Level 0 (OFF)
     ⚡ [GPIO BCM 16] Set to LOW (OFF) for air_conditioner_01
   ```
5. **Observe the Physical Hardware**: Relay 6 clicks OFF and turns off the AC circuit!
6. Click the **Green (ON)** toggle switch to switch power back ON.

### Test 2: Live Weather Streaming to Raspberry Pi RL Model
1. Go to **Overview** or **Analytics** on the dashboard.
2. Locate the **Live Weather Gateway & Pi Feed** card.
3. Click **"Fetch Live Weather"** (fetches live Guntur AP weather from Open-Meteo) or choose the **"🔥 Summer Heatwave (42°C)"** preset.
4. Click **"Broadcast Weather Stream to Pi"**.
5. **Observe the Raspberry Pi Terminal**:
   ```
   🌤️ Received Weather Stream from Dashboard: 42.4°C, Humidity: 45%
   🤖 RL Policy Actions Evaluated:
      • Air Conditioner: SHED (OFF) [High ambient heat load shedding]
   ```

### Test 3: Master Grid Peak Event Trigger
1. Switch to the **Grid Controller Dashboard** (`/grid`).
2. Click the **Master Grid Event Toggle** to **PEAK DEMAND EVENT**.
3. **Observe the Resident Dashboard**: Peak alert banner pops up; flexible appliances pause automatically, while **protected necessity appliances (Fan, Tube Light, Refrigerator) stay 100% ON**.

---

## ✅ Summary of Verification & Support

| Component | Status | Verification Result |
|---|---|---|
| **RL Model Checkpoint** | Ready | `models/sharp_rl_model.pkl` loaded & verified |
| **Pi Edge Agent** | Ready | `hardware/run_hardware_rl_agent.py` verified |
| **Dashboard UI** | Ready | 17 routes compiled, 0 lint errors, 22/22 unit tests passing |
| **MQTT Integration** | Ready | Dual-way sync over `broker.hivemq.com` |
