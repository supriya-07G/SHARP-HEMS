# Runbook — peak scenarios on the SHARP rig

How to run the four peak scenarios end to end: Raspberry Pi agent, runtime
bridge, scenario service, and the dashboard.

**Product mode is the normal way to run SHARP** (section 0): set the Pi up
once, then everything is done from the dashboard. The Pi and the laptop do not
need the same Wi-Fi, and nobody has to SSH in. The manual SSH commands are
kept as a fallback (section 3).

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

## 0. Product mode: set up once, then use only the dashboard

Three services run on the Pi and start at every boot:

| Service | Script | Job |
|---|---|---|
| `sharp-pi-agent` | `hardware/pi_agent.py` | GPIO, RL policy, safety shield |
| `sharp-runtime-bridge` | `hardware/runtime_bridge.py` | What the dashboard displays |
| `sharp-scenario` | `hardware/scenario_service.py` | Applies the scenario chosen on the dashboard |

Each one restarts if it stops and keeps retrying until the broker answers, so
a slow Wi-Fi at boot is fine. Everything travels through HiveMQ Cloud: the Pi
only needs internet, on any Wi-Fi it knows.

### One-time install (on the Pi, over SSH)

```bash
cd ~/SHARP-HEMS
git status --short                      # must print nothing; tell the team if it lists files
git fetch origin
git checkout <the merged branch> && git pull
source .venv/bin/activate
pip install -r hardware/requirements_pi.txt
sed -i 's/^MQTT_PORT=.*/MQTT_PORT=8884/' .env     # WebSockets port
grep -q '^MQTT_TRANSPORT=' .env || echo 'MQTT_TRANSPORT=websockets' >> .env
bash hardware/install_services.sh
```

The installer checks the virtualenv, the packages, `.env` and the port before
it changes anything, and stops with the exact fix if one is wrong. It also
stops any copies started by hand, so nothing runs twice.

### Every day after that

1. Power on the Pi. Within about a minute the dashboard header reads **live**.
2. **Technical → House scenario:** pick Normal, Household peak, Grid peak or
   Grid + household peak. The card shows what the Pi actually applied
   ("Active: … · applied HH:MM:SS IST").
3. **Grid Control:** declare or cancel a grid peak (severity 0.60 or more).
4. **My Home:** watch the appliances, respond to the peak notice, check the bill.

The last scenario chosen is kept on the broker, so a Pi that reboots resumes
it. With none chosen it starts in Normal.

### Check or control the services (over SSH, when needed)

```bash
systemctl status sharp-pi-agent sharp-runtime-bridge sharp-scenario --no-pager
journalctl -u sharp-pi-agent -n 50 --no-pager        # last 50 agent log lines
journalctl -u sharp-pi-agent -f                      # follow live (Ctrl-C to stop)
sudo systemctl restart sharp-pi-agent sharp-runtime-bridge sharp-scenario
sudo systemctl disable --now sharp-pi-agent sharp-runtime-bridge sharp-scenario   # back to manual mode
```

After changing code (`git pull`), restart the three services.

## 1. One-time setup

### Broker settings (`.env` at the repo root, used by every Python script)

```bash
MQTT_HOST=<your HiveMQ cluster host>
MQTT_TRANSPORT=websockets
MQTT_PORT=8884
MQTT_USER=<user>
MQTT_PASS=<password>
HOUSE_ID=demo
```

The scripts connect over secure WebSockets on port 8884, which passes networks
that block MQTT's usual port 8883. (`MQTT_TRANSPORT=tcp` with `MQTT_PORT=8883`
still works where 8883 is open.) WebSockets on 8883 never connects; the
installer refuses that combination. `HOUSE_ID` must be the same here and in
the dashboard's `NEXT_PUBLIC_HOUSE_ID`, or the dashboard will never see the
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
below this is not a grid peak.

There is **no manual hold**. The RL loop decides for all ten appliances on
every state it receives. A resident's switch is remembered as their choice and
the policy applies it on every decision: with no peak it stands; during a peak
an unpaid luxury load is still shed. Publishing a *different* scenario resets
the house to that scenario's baseline. (`MANUAL_OVERRIDE_HOLD_SECONDS` is no
longer read.)

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
python hardware/test_scenario_service.py # dashboard scenario requests -> house state
```

Each one ends with a `✅ … PASSED` / `OK` line. If any fails, stop here.

## 3. Fallback: start the system by hand (over SSH)

Use this only if product mode is not installed, or a service will not start.
If the services are installed, stop them first, or every command is answered
twice:

```bash
sudo systemctl stop sharp-pi-agent sharp-runtime-bridge sharp-scenario
```

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

In product mode, pick the scenario on **Technical → House scenario**. In
manual mode (section 3), publish it from any machine with the repo and `.env`:

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

**End it:** publish `normal`. The Pi logs `🏠 Household peak ended` and
`🔄 Scenario normal → resident choices reset`. The house returns to the normal
baseline: fridge, TV, fan and lights on; AC and EV off.

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
| `home/<house>/scenario/set`         | dashboard `/api/scenario` (retained) | Scenario chosen on the dashboard                          |
| `home/<house>/scenario/active`      | `scenario_service.py` (retained) | Scenario the Pi actually applied, and when                      |

The `intent` message's `shield_reasons` says why each luxury load ended up
where it did: `grid_peak_luxury_shed`, `household_peak_luxury_shed`,
`peak_surcharge_paid`, `no_peak_luxury_kept_on`, `luxury_not_requested`.

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `socket.gaierror: Temporary failure in name resolution` (old code), or `🌐 Cannot resolve …` repeating (current code) | The Pi has no working DNS/internet: a network problem, not SHARP code. On the Pi: `ping -c 2 8.8.8.8` (internet?), then `getent hosts <MQTT_HOST>` (DNS?). The agent and bridge keep retrying and connect by themselves once the network works |
| Pi banner says `Hold : 900s after resident override` | The Pi is running old code. Copy the current `hardware/` folder to it (see below) |
| Dashboard stuck on "Waiting for Raspberry Pi telemetry" | `runtime_bridge.py` not running, or `NEXT_PUBLIC_HOUSE_ID` ≠ `HOUSE_ID` |
| Publishing a scenario changes nothing | Agent/bridge started after the publish (state isn't retained): publish again |
| Grid peak declared but nothing happens | Severity below 0.60, or the 40-second warning is still running |
| Luxury load never sheds in a peak | The resident paid for it (it is in `opted_out`), or the grid peak is still in its warning |
| Header shows "N min old" / "MQTT DISCONNECTED (Retained State)" | `runtime_bridge.py` is not running: the dashboard is showing the last retained state |
| "Raspberry Pi agent is offline" notice; switches report "No reply from the Raspberry Pi" after 15 s | `pi_agent.py` is not running or not connected |
| A peak alert from an earlier run is still showing | It disappears when the Pi reconnects: on connect the Pi replaces the retained peak status |
| No RL decisions at all | `RL_ENABLED=false`, or the model file is missing (agent logs `❌ RL enabled but model is not loaded`) |
| OLED blank | I2C off, wrong address, or `luma.oled`/`pillow` not installed (agent logs `⚠️ OLED unavailable`) |
| Grid peak shows on the dashboard but the Pi ignores it | Pi and dashboard on different `HOUSE_ID`s |

## 8. Getting the current code onto the Pi without GitHub

The Pi and the laptop do **not** need to share a network to run SHARP: each
only needs internet to reach the HiveMQ broker. Copying code is different.

If the Pi cannot reach GitHub (no DNS) or the branch is not pushed yet, join
the laptop to the **same Wi-Fi as the Pi** for a minute and copy the
`hardware/` folder over it. `pi.local` works on that network even without
internet. From PowerShell on the laptop:

```bash
scp -r "C:\Users\SUPRIYA\SHARP_Master_Dataset\.claude\worktrees\continue-changes-18e03d\hardware" pi@pi.local:~/SHARP-HEMS/
```

This overwrites the Pi's `~/SHARP-HEMS/hardware/` files with the laptop's;
the Pi's `.env` and `models/` are not touched. Check it worked: the agent
banner should say `Hold   : none - RL decides every appliance on every state`.
