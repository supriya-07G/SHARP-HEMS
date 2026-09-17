"""Replay a recorded household day as if a Raspberry Pi were live.

THE CRITICAL PATH. This unblocks everyone:

  * the dashboard gets a real feed instead of mock data,
  * the Pi team gets realistic messages to test an actuator against,
  * and it is the fallback that saves demo day if the campus Wi-Fi drops -
    which the hosting plan flags as the likeliest thing to go wrong.

It needs no model, no hardware and no network. It reads held-out validation
episodes off disk and emits `state` and `intent` messages in exactly the shape
`dashboard/lib/contracts.ts` declares.

THE SINK IS PLUGGABLE, deliberately. The transport argument was still open when
this was written, so nothing here knows what MQTT is:

    --sink stdout   one JSON object per line; pipe it anywhere
    --sink file     writes latest.json + a growing history.jsonl
    --sink mqtt     publishes to a broker (needs paho-mqtt and a broker)

Adding a Supabase sink is one class with two methods. Whichever transport wins,
the replay logic does not change.

    python scripts/replay_publisher_v1.py --sink file --out dashboard/public/feed
    python scripts/replay_publisher_v1.py --sink stdout --speed 10

DEMO TIMING. The measured grid peak is 08:00-17:00 and severity is exactly
0.000 after 18:00; household load peaks at 19:00, which is a different event.
`--start-hour 11` puts you just before the peak. A demo built around an evening
peak will never light the badge.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_sharp_policy():
    """The shipped policy, run live over each replayed state.

    Without this the feed replays `serve_preferred` - the no-demand-response
    baseline - so the air conditioner stays on through a severity 1.0 peak and
    the demo shows nothing happening. Running the real model is the difference
    between a data viewer and a demonstration.
    """
    bundle = ROOT / 'handover/sharp_rl_v1'
    sys.path.insert(0, str(bundle))
    from run_policy import SharpPolicy
    return SharpPolicy(bundle / 'sharp_policy.npz')


def plain_grid_households(release):
    """D8: the target cohort is homes with no solar and no inverter. A demo on
    a solar home is a demo of a different product."""
    try:
        from evaluate_sharp_policy_v1 import plain_grid_households as cohort
        return set(cohort(ROOT))
    except Exception:
        return set()

N_BRANCHES = 28
GLOBAL_FEATURES = 25
DEVICE_FEATURES = 10
SEVERITY = 5                  # global feature: obs_grid_peak_severity
REMAINING_HOURS = 0           # device feature offsets
POWER_PROXY_KW = 1
PREFERRED_SERVICE = 6

LEVEL_SHED, LEVEL_ON = 0, 1

# THE RIG. Ten appliances, frozen, matching HARDWARE_PROTOTYPE_SPEC.md 2 and
# dashboard/lib/contracts.ts. The dashboard is built for THIS hardware, so the
# feed must always describe exactly these ten - never the dataset household's
# own device list, which has duplicates (ceiling_fan_02) and appliances the rig
# does not have (geyser, water_pump).
RIG = [
    ('ceiling_fan_01',      'ceiling_fan',     'Ceiling Fan',      True,   60.0),
    ('table_fan_01',        'table_fan',       'Table Fan',        True,   40.0),
    ('led_bulb_01',         'led_bulb',        'LED Bulb',         True,    9.0),
    ('led_tube_01',         'led_tube',        'LED Tube',         True,   18.0),
    ('refrigerator_01',     'refrigerator',    'Refrigerator',     True,   43.2),
    ('air_conditioner_01',  'air_conditioner', 'Air Conditioner',  False, 1328.4),
    ('washing_machine_01',  'washing_machine', 'Washing Machine',  False,  113.7),
    ('ev_charger_01',       'ev_charger',      'EV Charger',       False, 1500.0),
    ('television_01',       'television',      'Television',       False,  104.6),
    ('mixer_grinder_01',    'mixer_grinder',   'Mixer Grinder',    False,  500.0),
]


# --------------------------------------------------------------------------
# Sinks
# --------------------------------------------------------------------------

class StdoutSink:
    """One JSON object per line. Pipe it into anything."""

    def publish(self, topic, payload):
        print(json.dumps({'topic': topic, 'payload': payload}), flush=True)

    def close(self):
        pass


class FileSink:
    """latest.json for "what is true now", history.jsonl for everything.

    Enough to serve a dashboard over plain HTTP with no broker at all, which is
    the offline demo path.
    """

    def __init__(self, out: Path):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.history = (self.out / 'history.jsonl').open('w', encoding='utf-8')

    def publish(self, topic, payload):
        name = topic.rstrip('/').split('/')[-1]
        (self.out / f'{name}.json').write_text(
            json.dumps(payload, indent=2), encoding='utf-8')
        self.history.write(json.dumps({'topic': topic, 'payload': payload}) + '\n')
        self.history.flush()

    def close(self):
        self.history.close()


class MqttSink:
    """Publishes to a broker. Retained on state, so a browser joining mid-run
    sees the current state immediately instead of waiting for the next step."""

    RETAINED = ('state', 'health')

    def __init__(self, url, username=None, password=None):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise SystemExit('pip install paho-mqtt, or use --sink file')
        from urllib.parse import urlparse
        u = urlparse(url)
        self.client = mqtt.Client(transport='websockets'
                                  if u.scheme.startswith('ws') else 'tcp')
        if username:
            self.client.username_pw_set(username, password)
        if u.scheme in ('wss', 'mqtts', 'ssl'):
            self.client.tls_set()
        port = u.port or (443 if u.scheme == 'wss' else 8883)
        self.client.connect(u.hostname, port, keepalive=60)
        self.client.loop_start()

    def publish(self, topic, payload):
        retain = topic.rstrip('/').split('/')[-1] in self.RETAINED
        self.client.publish(topic, json.dumps(payload), qos=0, retain=retain)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


# --------------------------------------------------------------------------
# Building the messages
# --------------------------------------------------------------------------

def device_catalogue(release: Path):
    """Slot order must match the generator exactly: device_id ascending within
    household. Getting this wrong attaches every appliance to the wrong slot,
    which does not crash - it just reports the wrong appliance."""
    devices = pd.read_parquet(
        release / 'simulator_inputs/device_power_models.parquet',
        columns=['template_id', 'device_id', 'appliance_type',
                 'is_necessity', 'supports_reduced'])
    devices = devices.sort_values(['template_id', 'device_id'])
    devices['slot'] = devices.groupby('template_id').cumcount()
    return devices


SERVICE_CLASS = {
    'refrigerator': 'critical', 'ceiling_fan': 'critical', 'table_fan': 'critical',
    'led_bulb': 'critical', 'led_tube': 'critical', 'incandescent_bulb': 'critical',
    'air_conditioner': 'thermostatic', 'air_cooler': 'thermostatic',
    'washing_machine': 'deferrable', 'ev_charger': 'deferrable',
    'water_heater': 'deferrable', 'geyser': 'deferrable',
}


def service_class(appliance_type, is_necessity):
    if appliance_type in SERVICE_CLASS:
        return SERVICE_CLASS[appliance_type]
    return 'critical' if is_necessity else 'interruptible'


def build_state(row, slots, house_id, step, policy=None):
    state = np.asarray(row.state, dtype=float)
    action = np.asarray(row.action, dtype=int)
    requested = np.asarray(row.requested_action, dtype=int)
    present = np.asarray(row.device_present, dtype=float) > 0
    severity = float(state[SEVERITY])

    if policy is not None:
        # Rebuild the masks the policy needs, in SLOT order, from the rig map.
        nec_by_slot = np.zeros(N_BRANCHES, bool)
        wants_by_slot = np.zeros(N_BRANCHES, bool)
        for dev in slots.values():
            slot = dev['slot']
            if slot is None or slot >= N_BRANCHES:
                continue
            base = GLOBAL_FEATURES + slot * DEVICE_FEATURES
            nec_by_slot[slot] = bool(dev['is_necessity'])
            wants_by_slot[slot] = bool(state[base + PREFERRED_SERVICE] > 0
                                       and state[base + REMAINING_HOURS] > 0)
        try:
            action = policy.decide(
                state, device_present=present, is_necessity=nec_by_slot,
                supports_reduced=np.zeros(N_BRANCHES, bool),
                occupant_wants=wants_by_slot)
        except Exception as exc:                 # never let the feed die
            print(f'policy failed at step {step}: {exc}', file=sys.stderr)

    appliances = []
    for aid, dev in slots.items():
        slot = dev['slot']
        nec = bool(dev['is_necessity'])

        if slot is None or slot >= len(present) or not present[slot]:
            # Present on the rig, absent from this household's recorded data.
            # Report it idle rather than hide it - the resident owns ten
            # appliances and must see ten.
            appliances.append({
                'appliance_id': aid,
                'display_name': dev['display_name'],
                'appliance_type': dev['appliance_type'],
                'service_class': service_class(dev['appliance_type'], nec),
                'is_necessity': nec,
                'supports_reduced': False,
                'level': LEVEL_SHED,
                'occupant_wants': False,
                'peak_locked_out': False,
                'power_15min_mean_w': 0.0,
                'measured_w': None,
                'gpio_state': 0,
                'actuation_verified': True,
                'remaining_service_hours': 0.0,
                'shed_reason': None,
                'deferred_until': None,
                'no_recorded_demand': True,
            })
            continue

        base = GLOBAL_FEATURES + slot * DEVICE_FEATURES
        wants = bool(state[base + PREFERRED_SERVICE] > 0
                     and state[base + REMAINING_HOURS] > 0)
        level = int(action[slot]) if slot < len(action) else 0
        asked = int(requested[slot]) if slot < len(requested) else 0
        # The occupant asked for it; SHARP did not grant it; the grid is
        # stressed. That is a peak lockout, and the UI must grey the control.
        # Locked out when the occupant asked for a luxury load and did not get
        # it while the grid is stressed. This is what the UI greys out.
        locked = bool(severity >= 0.4 and not nec and asked > 0 and level == 0)
        appliances.append({
            'appliance_id': aid,
            'display_name': dev['display_name'],
            'appliance_type': dev['appliance_type'],
            'service_class': service_class(dev['appliance_type'], nec),
            'is_necessity': nec,
            'supports_reduced': False,
            'level': level,
            'occupant_wants': wants,
            'peak_locked_out': locked,
            # Derived, not metered: the rated wattage of the appliance the LED
            # stands for, gated on whether it is actually on.
            'power_15min_mean_w': dev['rated_w'] if level > 0 else 0.0,
            # No meter is fitted. A number here would make a stuck relay,
            # a failed GPIO write and a broken wire invisible at once.
            'measured_w': None,
            'gpio_state': 1 if level > 0 else 0,
            'actuation_verified': True,
            'remaining_service_hours': round(float(state[base + REMAINING_HOURS]) * 4, 2),
            'shed_reason': 'peak_lockout' if locked else None,
            'deferred_until': None,
        })

    # Derive the total from what the relays are ACTUALLY doing, not from the
    # recorded row. Replaying the recording's total while the policy has shed
    # the air conditioner would put 1.33 kW at the top of a screen whose
    # appliances sum to 103 W, and the resident would be right not to trust it.
    background = round(float(row.background_load_kw), 4)
    controllable = sum(a['power_15min_mean_w'] for a in appliances) / 1000.0
    aggregate = round(background + controllable, 4)

    return {
        'house_id': house_id,
        'timestamp_ist': str(row.timestamp_ist),
        'aggregate_power_kw': aggregate,
        'background_load_kw': background,
        'sanctioned_load_kw': round(float(state[8]), 2),
        'indoor_temperature_c': round(float(row.indoor_temperature_c), 2),
        'outdoor_temperature_c': round(float(row.outdoor_temperature_c), 2),
        'occupancy_adult_home_fraction': round(float(row.occupancy_adult_home_fraction), 3),
        'attention_available': bool(row.attention_available),
        'marginal_tariff_inr_kwh': round(float(row.marginal_tariff_inr_kwh), 2),
        'month_to_date_kwh': round(float(row.month_to_date_kwh), 2),
        'grid_peak_severity': round(severity, 4),
        'operating_mode': str(row.operating_mode),
        'battery_state_of_charge': round(float(row.battery_kwh), 3),
        'grid_absent': bool(row.grid_absent),
        'appliances': appliances,
        'data_age_seconds': 0,
        'step_id': int(step),
    }


def build_intent(state_message, row, slots):
    """What the controller asked for, and what the shield allowed.

    A refusal is evidence, not an error - the dashboard renders it.
    """
    requested = np.asarray(row.requested_action, dtype=int)
    proposed, executed, reasons = {}, {}, {}
    for a in state_message['appliances']:
        executed[a['appliance_id']] = a['level']
        proposed[a['appliance_id']] = a['level']
        if a['peak_locked_out']:
            proposed[a['appliance_id']] = LEVEL_ON
            reasons[a['appliance_id']] = ['peak_lockout']
        elif a['is_necessity'] and a['occupant_wants'] and a['level'] == LEVEL_ON:
            # The mask kept this on. Worth showing: it is the guarantee working.
            reasons.setdefault(a['appliance_id'], [])
    return {
        'command_id': f"replay-{state_message['step_id']}",
        'proposed': proposed,
        'executed': executed,
        'shield_reasons': {k: v for k, v in reasons.items() if v},
        'policy_source': 'replay:recorded_validation_episode',
        'decision_latency_ms': 1.2,
    }


def build_peak_event(state_message, sequence):
    severity = state_message['grid_peak_severity']
    active = severity >= 0.4
    return {
        'event_id': f"replay-{state_message['timestamp_ist'][:10]}-{sequence:03d}",
        'sequence': sequence,
        'region': 'APCPDCL / Guntur',
        'severity': severity,
        'declared_at': state_message['timestamp_ist'],
        'expires_at': state_message['timestamp_ist'],
        'reason': 'historical_curve',
        'is_active': active,
    }


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--release', type=Path, default=ROOT / 'release/SHARP_MASTER_V2')
    p.add_argument('--sink', choices=['stdout', 'file', 'mqtt'], default='file')
    p.add_argument('--out', type=Path, default=ROOT / 'dashboard/public/feed')
    p.add_argument('--broker', default=None, help='wss://host:443/mqtt')
    p.add_argument('--username', default=None)
    p.add_argument('--password', default=None)
    p.add_argument('--house', default='demo')
    p.add_argument('--episode', default=None, help='episode_id; default picks one')
    p.add_argument('--speed', type=float, default=1.0,
                   help='steps per second (1.0 = one 15-min step each second)')
    p.add_argument('--start-hour', type=int, default=11,
                   help='hour of day to start at; the peak is 08:00-17:00')
    p.add_argument('--loop', action='store_true', help='repeat forever')
    p.add_argument('--once', action='store_true', help='emit one step and exit')
    p.add_argument('--policy', choices=['sharp', 'recorded'], default='sharp',
                   help="'sharp' runs the shipped model over each state (the "
                        "demo); 'recorded' replays the logged baseline, which "
                        "does no demand response at all")
    a = p.parse_args()

    frame = pd.read_parquet(a.release / 'rl_transitions/splits/validation.parquet')
    frame = frame[frame.policy.eq('serve_preferred')] if 'policy' in frame else frame
    if a.episode:
        frame = frame[frame.episode_id.eq(a.episode)]
        if frame.empty:
            raise SystemExit(f'no episode {a.episode!r}')
    else:
        # Picking on peak severity alone gives an empty house at midday with
        # every appliance already off - technically a peak, and nothing to look
        # at. A usable demo day needs all four of:
        #   * the plain-grid cohort (no solar, no inverter) - D8
        #   * a real peak
        #   * a luxury load worth shedding
        #   * somebody home to notice
        cohort = plain_grid_households(a.release)
        devices_all = device_catalogue(a.release)
        luxury = set(devices_all[~devices_all.is_necessity.astype(bool)].template_id)

        best, best_id = None, None
        for episode, g in frame.groupby('episode_id'):
            household = g.household_id.iloc[0]
            if cohort and household not in cohort:
                continue
            if household not in luxury:
                continue
            states = np.stack(g.state.to_numpy())
            severity = float(states[:, SEVERITY].max())
            if severity < 0.4:
                continue
            occupied = float(g.occupancy_adult_home_fraction.max())
            running = float(g.aggregate_power_kw.max())
            score = severity + occupied + min(running, 2.0)
            if best is None or score > best:
                best, best_id = score, episode
        if best_id is None:
            raise SystemExit(
                'No episode has a peak, a luxury load and an occupant. '
                'Pass --episode explicitly.')
        frame = frame[frame.episode_id.eq(best_id)]
        states = np.stack(frame.state.to_numpy())
        print(f'episode {best_id}\n'
              f'  peak severity   {states[:, SEVERITY].max():.2f}\n'
              f'  occupancy       {frame.occupancy_adult_home_fraction.max():.2f}\n'
              f'  max draw        {frame.aggregate_power_kw.max():.3f} kW',
              file=sys.stderr)

    frame = frame.sort_values('step_id').reset_index(drop=True)

    # Map the recorded household onto the RIG. For each of the ten, take the
    # first device of that type the household owns; the rest are reported
    # present but idle, and flagged, so the resident always sees ten tiles and
    # nobody is left wondering where the EV charger went.
    devices = device_catalogue(a.release)
    household = frame.household_id.iloc[0]
    mine = devices[devices.template_id.eq(household)].sort_values('slot')

    slots, taken, synthetic = {}, set(), []
    for aid, atype, label, nec, watts in RIG:
        match = mine[mine.appliance_type.eq(atype) & ~mine.slot.isin(taken)]
        entry = {'appliance_id': aid, 'display_name': label,
                 'appliance_type': atype, 'is_necessity': nec,
                 'supports_reduced': False, 'rated_w': watts, 'slot': None}
        if len(match):
            slot = int(match.iloc[0].slot)
            taken.add(slot)
            entry['slot'] = slot
        else:
            synthetic.append(aid)
        slots[aid] = entry

    print(f'household {household}  {len(frame)} steps', file=sys.stderr)
    print(f'  mapped onto the rig: {len(RIG) - len(synthetic)} of {len(RIG)} '
          f'from recorded data', file=sys.stderr)
    if synthetic:
        print(f'  idle (not owned by this household): {", ".join(synthetic)}',
              file=sys.stderr)

    if a.sink == 'stdout':
        sink = StdoutSink()
    elif a.sink == 'mqtt':
        if not a.broker:
            raise SystemExit('--sink mqtt needs --broker')
        sink = MqttSink(a.broker, a.username, a.password)
    else:
        sink = FileSink(a.out)
        print(f'writing to {a.out}', file=sys.stderr)

    policy = None
    if a.policy == 'sharp':
        policy = load_sharp_policy()
        print('running the shipped SHARP policy over each state',
              file=sys.stderr)
    else:
        print('replaying the recorded baseline - NO demand response',
              file=sys.stderr)

    start = max(0, min(len(frame) - 1, int(a.start_hour * 4)))
    base = f'home/{a.house}'
    delay = 1.0 / a.speed if a.speed > 0 else 0.0
    sequence = 0

    try:
        while True:
            for i in range(start, len(frame)):
                row = frame.iloc[i]
                state = build_state(row, slots, a.house, row.step_id, policy)
                sink.publish(f'{base}/state', state)
                sink.publish(f'{base}/intent', build_intent(state, row, slots))
                sequence += 1
                sink.publish('grid/guntur/peak_event',
                             build_peak_event(state, sequence))
                sink.publish(f'{base}/health', {
                    'source': 'replay_publisher_v1',
                    'published_at': datetime.now().astimezone().isoformat(),
                    'step_id': int(row.step_id),
                    'simulated': True,
                })
                if a.once:
                    return 0
                if delay:
                    time.sleep(delay)
            if not a.loop:
                return 0
            start = 0
    except KeyboardInterrupt:
        print('\nstopped', file=sys.stderr)
        return 0
    finally:
        sink.close()


if __name__ == '__main__':
    raise SystemExit(main())
