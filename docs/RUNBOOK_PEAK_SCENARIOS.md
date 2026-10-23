# Runbook — peak scenarios on the SHARP rig

How to run the four peak scenarios end to end: Raspberry Pi agent, runtime
bridge, dashboard, and the mock house state.

## The four scenarios

| Scenario (`--scenario`)   | Grid peak | Household peak | Luxury loads (AC, EV, washer, mixer, TV) |
|---------------------------|-----------|----------------|-------------------------------------------|
| `grid_and_household_peak` | yes       | yes            | shed                                      |
| `grid_peak`               | yes       | no             | shed after the 40-second warning          |
| `household_peak`          | no        | yes            | shed in this house only                   |
| `normal`                  | no        | no             | left exactly as they are                  |

- **Grid peak** is declared from the dashboard's **Grid Controller**, never by
  the mock script. `grid_peak` and `grid_and_household_peak` only set up the
  house; you still declare the peak.
- **Household peak** is the `household_peak` flag in the house's own state.
- **Starting state.** In every peak scenario all ten appliances start ON, so
  you can watch the Pi switch the luxury loads off. In `normal`, the fridge,
  TV, ceiling fan and both lights are ON and everything else is OFF.
- **Essential loads** (fridge, fans, lights) are never shed by a peak.
- **Paying to keep a load on.** During any peak the resident can tap *Keep on*
  or switch a luxury load on, accept the ₹12.40 surcharge, and the Pi keeps it
  running. The surcharge is a proposal, not an APCPDCL tariff today.
- `peak` is an older name for `grid_peak` and still works.

## 1. One-time setup

### Broker settings (`.env` at the repo root, used by every Python script)

```bash
MQTT_HOST=<your HiveMQ cluster host>
MQTT_PORT=8883
MQTT_USER=<user>
MQTT_PASS=<password>
HOUSE_ID=house_01
```

The scripts connect over TLS (port 8883). `HOUSE_ID` must be the same here and
in the dashboard's `NEXT_PUBLIC_HOUSE_ID`, or the dashboard will never see the
house.

### Pi-only settings (add to the Pi's `.env`)

```bash
GPIO_ENABLED=true
RL_ENABLED=true
OLED_ENABLED=true
# Warning before a grid peak sheds luxury loads. Default 40 s (demo).
# Use 600 for the real 10-minute notice.
PEAK_WARNING_SECONDS=40
```

Optional: `GRID_PEAK_POLICY_THRESHOLD` (default `0.60`): a declared severity
below this is not a grid peak. `MANUAL_OVERRIDE_HOLD_SECONDS` (default `900`) is
how long a resident's switch overrides the RL loop.

The model is read from `models/sharp_rl_model.pkl` unless `PKL_MODEL_PATH` says
otherwise. The RL loop does nothing without it.

### Pi packages

```bash
pip install -r hardware/requirements_pi.txt
pip install luma.oled pillow   # only for the SSD1306 OLED
```

Enable I2C (`sudo raspi-config` → Interface Options → I2C) for the OLED at
address `0x3C` on I2C port 1.

### Dashboard (`dashboard/.env.local`)

```bash
NEXT_PUBLIC_HOUSE_ID=house_01
NEXT_PUBLIC_MQTT_URL=wss://<your HiveMQ host>:8884/mqtt
NEXT_PUBLIC_MQTT_USER=<read-only user>
NEXT_PUBLIC_MQTT_PASS=<read-only password>
# Server-side only: used to publish grid events and overrides.
MQTT_URL=wss://<your HiveMQ host>:8884/mqtt
MQTT_PUBLISH_USER=<publish user>
MQTT_PUBLISH_PASS=<publish password>
```

Anything starting with `NEXT_PUBLIC_` is visible to everyone who opens the
dashboard, so it should be a read-only broker user.

## 2. Check it offline first (no broker, no GPIO)

From the repo root, on the Pi or a laptop:

```bash
python hardware/test_pkl_mock.py        # model loads; 4 scenarios give the right luxury outcome
python hardware/test_peak_warning.py    # warning -> active -> cancel/expiry, bridge lockout, OLED text
python hardware/test_four_scenarios.py  # all 4 scenarios through the Pi's message handlers
```

Each one ends with a `✅ … PASSED` / `OK` line. If any fails, stop here.

## 3. Start the system (in this order)

Start the Pi agent and bridge **before** publishing any house state. The mock
state is not retained, so a process that is not running yet misses it.

```bash
# Terminal 1 (Pi): agent - GPIO, RL, OLED
python hardware/pi_agent.py

# Terminal 2 (Pi): runtime bridge - what the dashboard displays
python hardware/runtime_bridge.py

# Terminal 3 (laptop): dashboard
cd dashboard
npm install
npm run dev
```

Open http://localhost:3000/resident (resident view) and
http://localhost:3000/grid (Grid Controller) in two tabs.

Wait until the agent logs `✅ Connected to HiveMQ` and the bridge is online.

## 4. Run each scenario

Publish a scenario from any machine with the repo and `.env`:

```bash
python hardware/mock_rl_state.py --scenario <name> --publish
```

To preview the state without publishing, use `--print-only`.

### A. `normal`: no peak, nothing shed

```bash
python hardware/mock_rl_state.py --scenario normal --publish
```

**Expect:** fridge, TV, ceiling fan, Light 1, Light 2 ON; AC, EV, washer,
mixer, USB fan OFF. OLED shows the normal pages.

**Then:** switch the AC and EV on from the resident dashboard (Appliances).
No surcharge dialog appears. Publish `normal` again: **they stay ON**. The Pi
logs `no_peak_luxury_kept_on`.

### B. `household_peak`: this house only

```bash
python hardware/mock_rl_state.py --scenario household_peak --publish
```

**Expect:** all appliances start ON, then the Pi logs
`🏠 HOUSEHOLD PEAK → shedding luxury loads in this house` and the AC, EV,
washer, mixer and TV go OFF. Essentials stay ON. The dashboard shows
**"Household peak in your home"**. The OLED shows `HOUSE PEAK (SHED)`.

**Pay to keep one on:** tap *Keep AC on* and confirm the ₹12.40 dialog. The
Pi logs `💳 Peak billing opt-out: air_conditioner_01` and the AC comes back
ON. The other luxury loads stay off.

**End it:** publish `normal`. The Pi logs `🏠 Household peak ended`. The TV
returns (normal has it on). The paid AC stays on. Other loads the peak shed
stay off until switched on again.

### C. `grid_peak`: declared from the Grid Controller

```bash
python hardware/mock_rl_state.py --scenario grid_peak --publish
```

The script prints `⚠️ Declare the grid peak from the dashboard's Grid
Controller`. Until you do, **everything stays ON**: a severity in the state is
not a grid peak.

On http://localhost:3000/grid:

1. Set **Requested severity** to **0.60 or higher** (e.g. 0.85).
2. Pick a duration (30, 60, 90 or 120 min).
3. Press **PUBLISH GRID EVENT**.

**Expect, warning phase:** Pi logs `⚠️ PEAK WARNING → 40s before luxury loads
are shed`. The dashboard counts down from 00:40. The OLED shows
`Shed in MM:SS`. **All loads stay ON** during the warning. Residents can pay
to keep loads on now.

**Expect, active phase** (after `PEAK_WARNING_SECONDS`): Pi logs
`🔴 GRID PEAK ACTIVE → Shedding unpaid luxury loads!`. Every luxury load not
paid for goes OFF and its dashboard switch locks behind the surcharge dialog.
The OLED shows `PEAK ACTIVE (SHED)`.

**End it:** press **CANCEL EVENT**, or let the duration run out (the Pi logs
`🟢 Grid event expired`). Luxury loads return to the house state (all ON in
this scenario).

### D. `grid_and_household_peak`: both

```bash
python hardware/mock_rl_state.py --scenario grid_and_household_peak --publish
```

**Expect:** the household peak sheds the luxury loads **immediately**, without
waiting for any grid warning. Then declare a grid peak as in C. Loads stay shed
through the warning and the active phase. Cancelling the grid peak does
**not** bring them back while the household peak is still on: the dashboard
switches to "Household peak in your home". Publish `normal` to end both.

## 5. Check the bill

Resident view → **Billing** tab. *Peak opt-out (N)* counts each device paid
for per peak, at ₹12.40 each. *Peak relief credit (N)* counts peaks you rode
through with at least one load paused. Counts come from what the Pi recorded,
not from button taps, and are kept per calendar month.

## 6. MQTT topics, for debugging

| Topic                               | Who publishes               | What                                                                 |
|-------------------------------------|-----------------------------|----------------------------------------------------------------------|
| `home/<house>/state`                | `mock_rl_state.py`          | House state, including `household_peak`                              |
| `home/<house>/grid/event`           | dashboard Grid Controller   | `declare` / `cancel`, severity, `expires_at`                         |
| `home/<house>/grid/warning`         | `pi_agent.py` (retained)    | Peak status: `warning` / `active` / `household` / `cancel`, `shed_at`, `opted_out` |
| `home/<house>/override/<appliance>` | dashboard                   | Resident switch / *Keep on*                                          |
| `home/<house>/intent`               | `pi_agent.py`               | RL proposal and the policy overrides applied                         |
| `home/<house>/runtime`              | `runtime_bridge.py` (retained) | What the dashboard shows, incl. `peak_locked_out`                 |

The `intent` message's `shield_reasons` says why each luxury load ended up
where it did: `grid_peak_luxury_shed`, `household_peak_luxury_shed`,
`peak_surcharge_paid`, `no_peak_luxury_kept_on`, `luxury_not_requested`.

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Dashboard stuck on "Waiting for Raspberry Pi telemetry" | `runtime_bridge.py` not running, or `NEXT_PUBLIC_HOUSE_ID` ≠ `HOUSE_ID` |
| Publishing a scenario changes nothing | Agent/bridge started after the publish (state isn't retained): publish again |
| Grid peak declared but nothing happens | Severity below 0.60, or the 40-second warning is still running |
| Luxury load never sheds in a peak | Resident paid for it, or it is inside the 15-minute manual-override hold |
| No RL decisions at all | `RL_ENABLED=false`, or the model file is missing (agent logs `❌ RL enabled but model is not loaded`) |
| OLED blank | I2C off, wrong address, or `luma.oled`/`pillow` not installed (agent logs `⚠️ OLED unavailable`) |
| Grid peak shows on the dashboard but the Pi ignores it | Pi and dashboard on different `HOUSE_ID`s |
