"""A selection objective that can be computed inside the Kaggle notebook.

THE PROBLEM THIS SOLVES
-----------------------
Pranitha's hyperparameter search (PR #1) is a good idea aimed at the wrong
target: it selects on balanced accuracy against the logged action. But the
logged action equals the occupant's request 96.35 % of the time, so that score
mostly measures how closely a controller reproduces DOING NOTHING. A search
that maximises it walks away from demand response.

The right target is peak reduction, and that needs the simulator - which cannot
run inside the training notebook. So we need a proxy computable from the
validation transitions alone, and we are only entitled to use it if it actually
predicts what the simulator says.

THE PROXY
---------
A useful controller sheds discretionary load WHEN THE GRID IS UNDER STRESS and
leaves it alone otherwise. Both halves matter: shedding during a peak is the
point, and shedding off-peak is pure loss - the occupant is inconvenienced and
no peak is avoided.

    peak_response  = mean FRACTION of available discretionary load shed,
                     over rows where severity >= T
    offpeak_noise  = the same fraction over rows where severity <  T
    TARGETING      = peak_response - offpeak_noise

The fraction, not raw kW. Raw kW is confounded: the peak band is 08:00-17:00,
when houses are empty and little discretionary load is running, while the
evening has far more on offer. Scored on raw kW every checkpoint here looks
like it sheds MORE off-peak than on-peak, which is an artefact of when load
exists rather than a fact about the controller.

Discretionary means: the occupant is asking for it, and it is not a necessity
load. Necessity loads are excluded because shedding one is a gate failure, not
a trade-off.

GATES (a candidate that fails these is out regardless of score):
    illegal greedy picks                 == 0
    necessity shed while occupant wants  == 0

VALIDATION
----------
Run with --validate to score every checkpoint here against the simulator
numbers in reports/final_model_selection_v1.json and report the rank
correlation. If the proxy does not track the simulator, it must not be used -
that check is the whole reason this file is separate and runnable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

N_BRANCHES = 28
N_LEVELS = 3
DEVICE_FEATURES = 10
GLOBAL_FEATURES = 25
REMAINING_HOURS = 0
POWER_PROXY_KW = 1
PREFERRED_SERVICE = 6
SEVERITY = 5                    # global feature: obs_grid_peak_severity

# The grid is in its stressed band. Measured peak hours are 08:00-17:00 and
# severity there runs 0.42-0.67, so 0.40 separates peak from the flat zero that
# holds after 18:00.
SEVERITY_THRESHOLD = 0.40


def forward(p, x):
    h = np.maximum(0, x @ p['w'] + p['b'])
    advantage = (h @ p['a'] + p['ab']).reshape(-1, N_BRANCHES, N_LEVELS)
    value = (h @ p['v'] + p['vb'])[:, :, None]
    return value + advantage - advantage.mean(2, keepdims=True)


def load_validation(release: Path):
    frame = pd.read_parquet(release / 'rl_transitions/splits/validation.parquet')
    state = np.stack(frame.state.to_numpy()).astype(np.float32)
    present = np.stack(frame.device_present.to_numpy()).astype(np.float32) > 0
    household = frame.household_id.to_numpy()

    devices = pd.read_parquet(
        release / 'simulator_inputs/device_power_models.parquet',
        columns=['template_id', 'device_id', 'is_necessity', 'supports_reduced'])
    devices = devices.sort_values(['template_id', 'device_id'])
    devices['slot'] = devices.groupby('template_id').cumcount()
    reduced = {(t, s): bool(v) for t, s, v in
               zip(devices.template_id, devices.slot, devices.supports_reduced)}
    nec = {(t, s): bool(v) for t, s, v in
           zip(devices.template_id, devices.slot, devices.is_necessity)}

    order = np.arange(N_BRANCHES)
    offset = order * DEVICE_FEATURES + GLOBAL_FEATURES

    necessity = np.stack([
        np.array([nec.get((h, s), False) for s in order]) for h in household])
    supports_reduced = np.stack([
        np.array([reduced.get((h, s), False) for s in order]) for h in household])

    wanted = ((state[:, offset + PREFERRED_SERVICE] > 0)
              & (state[:, offset + REMAINING_HOURS] > 0))
    power = state[:, offset + POWER_PROXY_KW]
    severity = state[:, SEVERITY]

    legal = np.ones((len(state), N_BRANCHES, N_LEVELS), dtype=bool)
    legal[:, :, 2] = supports_reduced
    deployment = legal.copy()
    deployment[:, :, 2] &= ~necessity                 # never dim an essential, ever
    deployment[:, :, 0] &= ~(necessity & wanted)      # never shed one in use

    return dict(state=state, present=present, necessity=necessity, wanted=wanted,
                power=power, severity=severity, legal=legal, deployment=deployment)


def score(data, checkpoint: Path, batch=8192):
    weights = np.load(checkpoint, allow_pickle=False)
    p = {k: weights[k] for k in ['w', 'b', 'v', 'vb', 'a', 'ab']}
    mean, sd = weights['mean'], weights['sd']

    greedy = np.zeros((len(data['state']), N_BRANCHES), dtype=np.int64)
    for i in range(0, len(data['state']), batch):
        chunk = ((data['state'][i:i + batch] - mean) / sd).astype(np.float32)
        q = forward(p, chunk)
        mask = data['present'][i:i + batch][:, :, None] & data['deployment'][i:i + batch]
        greedy[i:i + batch] = np.argmax(np.where(mask, q, -np.inf), axis=2)

    live = data['present']
    shed = (greedy == 0) & live
    discretionary = data['wanted'] & ~data['necessity'] & live

    # Gates
    illegal = int((~np.take_along_axis(data['legal'], greedy[:, :, None], axis=2)[:, :, 0]
                   & live).sum())
    entitled = data['necessity'] & data['wanted'] & live
    necessity_shed = int((entitled & (greedy == 0)).sum())

    # Normalise by the discretionary load that was actually AVAILABLE to shed.
    # Raw kW is confounded: the peak band is 08:00-17:00, when houses are empty
    # and little discretionary load is running, while the evening has far more
    # on offer. Comparing raw kW then measures when load exists, not when the
    # controller acts. The fraction of available load shed is the honest form.
    shed_kw = (data['power'] * (shed & discretionary)).sum(axis=1)
    available_kw = (data['power'] * discretionary).sum(axis=1)
    usable = available_kw > 1e-9
    fraction = np.zeros(len(shed_kw))
    fraction[usable] = shed_kw[usable] / available_kw[usable]

    peak_rows = (data['severity'] >= SEVERITY_THRESHOLD) & usable
    off_rows = (data['severity'] < SEVERITY_THRESHOLD) & usable
    peak_response = float(fraction[peak_rows].mean()) if peak_rows.any() else 0.0
    offpeak_noise = float(fraction[off_rows].mean()) if off_rows.any() else 0.0

    return {
        'checkpoint': checkpoint.name,
        'peak_response_kw': peak_response,
        'offpeak_noise_kw': offpeak_noise,
        'targeting': peak_response - offpeak_noise,
        'illegal_greedy_picks': illegal,
        'necessity_shed_while_entitled': necessity_shed,
        'peak_rows': int(peak_rows.sum()),
        'offpeak_rows': int(off_rows.sum()),
        'gates_pass': illegal == 0 and necessity_shed == 0,
    }


CANDIDATES = {
    'shipped (handover)': 'handover/sharp_rl_v1/sharp_policy.npz',
    'reward_driven': 'models/reward_driven.npz',
    'candidate_pranitha_config': 'models/candidate_pranitha_config.npz',
    'sweep_2.5': 'models/sweep_2.5.npz',
    'sweep_5.0': 'models/sweep_5.0.npz',
}


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    a.add_argument('--release', type=Path, default=None)
    a.add_argument('--validate', action='store_true',
                   help='check the proxy against the simulator ranking')
    args = a.parse_args()
    root = args.root.resolve()
    release = args.release or root / 'release/SHARP_MASTER_V2'

    data = load_validation(release)
    print(f'{len(data["state"]):,} validation rows, '
          f'{int((data["severity"] >= SEVERITY_THRESHOLD).sum()):,} in the peak band\n')

    rows = {}
    for label, relative in CANDIDATES.items():
        path = root / relative
        if not path.exists():
            continue
        rows[label] = score(data, path)
        r = rows[label]
        print(f'{label:28s} targeting {r["targeting"]:8.5f}  '
              f'peak {r["peak_response_kw"]:.5f}  offpeak {r["offpeak_noise_kw"]:.5f}  '
              f'gates {"PASS" if r["gates_pass"] else "FAIL"}')

    if not args.validate:
        return 0

    selection = root / 'reports/final_model_selection_v1.json'
    if not selection.exists():
        print('\nNo simulator results yet - run final_model_selection_v1.py first.')
        return 1
    truth = json.loads(selection.read_text(encoding='utf-8'))['absolute_means']

    shared = [l for l in rows if l in truth]
    proxy = np.array([rows[l]['targeting'] for l in shared])
    peak = np.array([truth[l]['peak_kw'] for l in shared])

    def rank(x):
        order = np.argsort(x)
        r = np.empty_like(order, dtype=float)
        r[order] = np.arange(len(x))
        return r

    # Higher targeting should mean LOWER simulator peak, so we expect a negative
    # correlation. Report it as agreement so the sign is not a trap.
    rp = rank(proxy)
    rt = rank(-peak)
    n = len(shared)
    spearman = (float(np.corrcoef(rp, rt)[0, 1]) if n > 2 and rp.std() > 0
                and rt.std() > 0 else float('nan'))

    print(f'\n{"=" * 70}\nPROXY VALIDATION against the simulator\n{"=" * 70}')
    print(f'{"candidate":28s} {"targeting":>10s} {"sim peak kW":>12s}')
    for l in sorted(shared, key=lambda l: -rows[l]['targeting']):
        print(f'{l:28s} {rows[l]["targeting"]:10.5f} {truth[l]["peak_kw"]:12.4f}')
    print(f'\nSpearman(targeting, -peak_kw) = {spearman:+.3f} over {n} checkpoints')
    if not np.isnan(spearman) and spearman >= 0.7:
        print('The proxy tracks the simulator. Safe to select on it in the notebook.')
    else:
        print('The proxy does NOT reliably track the simulator.')
        print('Do not select on it. Keep selection in the simulator, offline.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
