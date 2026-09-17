"""Score any checkpoint the way the DEPLOYED system will actually behave.

WHY THIS EXISTS
---------------
train_sharp_bdq_v3.py evaluates under the PHYSICAL mask only: level 2 is allowed
wherever the appliance can technically dim, which is 2,460 of 4,124 devices -
mostly ceiling fans, LED bulbs and tubes.

The deployed system does not allow that. The deployment mask says:

    a critical load is never DIMMED, ever, whether or not it is wanted
    a critical load is never SHED while the occupant is asking for it

After that mask, only 44 air coolers can be dimmed at all.

So a balanced accuracy measured under the physical mask is not comparable to one
measured under the deployment mask, and it is the higher of the two - the model
gets credit for choosing actions the Pi will never execute. Measured on one
checkpoint: 0.7525 physical against 0.6232 deployment. Quoting the first as an
improvement over the second would be inflating the headline with behaviour that
cannot ship.

This scores both, side by side, so the gap is visible rather than assumed.
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
PREFERRED_SERVICE = 6
LEVEL_NAMES = ['off', 'on', 'reduced']


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

    actions = np.zeros((len(frame), N_BRANCHES), dtype=np.int64)
    for row, levels in enumerate(frame.action.to_numpy()):
        levels = np.asarray(levels, dtype=np.int64)
        actions[row, :levels.size] = levels

    devices = pd.read_parquet(
        release / 'simulator_inputs/device_power_models.parquet',
        columns=['template_id', 'device_id', 'is_necessity', 'supports_reduced'])
    devices = devices.sort_values(['template_id', 'device_id'])
    devices['slot'] = devices.groupby('template_id').cumcount()
    red = {(t, s): bool(v) for t, s, v in
           zip(devices.template_id, devices.slot, devices.supports_reduced)}
    nec = {(t, s): bool(v) for t, s, v in
           zip(devices.template_id, devices.slot, devices.is_necessity)}

    slots = np.arange(N_BRANCHES)
    offset = slots * DEVICE_FEATURES + GLOBAL_FEATURES
    necessity = np.stack([np.array([nec.get((h, s), False) for s in slots])
                          for h in household])
    supports = np.stack([np.array([red.get((h, s), False) for s in slots])
                         for h in household])
    wanted = ((state[:, offset + PREFERRED_SERVICE] > 0)
              & (state[:, offset + REMAINING_HOURS] > 0))

    physical = np.ones((len(state), N_BRANCHES, N_LEVELS), dtype=bool)
    physical[:, :, 2] = supports
    deployment = physical.copy()
    deployment[:, :, 2] &= ~necessity
    deployment[:, :, 0] &= ~(necessity & wanted)

    return dict(state=state, present=present, actions=actions,
                physical=physical, deployment=deployment,
                necessity=necessity, wanted=wanted)


def metrics(data, greedy, mask_name):
    live = data['present']
    recall, logged, greedy_share = [], [], []
    for level in range(N_LEVELS):
        picked = live & (data['actions'] == level)
        n = picked.sum()
        logged.append(float(n / max(1, live.sum())))
        recall.append(float((picked & (greedy == level)).sum() / max(1, n)))
        greedy_share.append(float((live & (greedy == level)).sum() / max(1, live.sum())))
    agree = float((live & (greedy == data['actions'])).sum() / max(1, live.sum()))

    entitled = data['necessity'] & data['wanted'] & live
    return {
        'mask': mask_name,
        'balanced_accuracy': float(np.mean(recall)),
        'raw_agreement': agree,
        'recall_by_level': dict(zip(LEVEL_NAMES, recall)),
        'greedy_share': dict(zip(LEVEL_NAMES, greedy_share)),
        'logged_share': dict(zip(LEVEL_NAMES, logged)),
        'necessity_shed_while_entitled': int((entitled & (greedy == 0)).sum()),
        'necessity_dimmed': int((live & data['necessity'] & (greedy == 2)).sum()),
    }


def score(data, checkpoint: Path, batch=8192):
    weights = np.load(checkpoint, allow_pickle=False)
    p = {k: weights[k] for k in ['w', 'b', 'v', 'vb', 'a', 'ab']}
    mean, sd = weights['mean'], weights['sd']

    out = {}
    for name in ('physical', 'deployment'):
        greedy = np.zeros((len(data['state']), N_BRANCHES), dtype=np.int64)
        for i in range(0, len(data['state']), batch):
            chunk = ((data['state'][i:i + batch] - mean) / sd).astype(np.float32)
            q = forward(p, chunk)
            allowed = data['present'][i:i + batch][:, :, None] & data[name][i:i + batch]
            greedy[i:i + batch] = np.argmax(np.where(allowed, q, -np.inf), axis=2)
        out[name] = metrics(data, greedy, name)
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    a.add_argument('--release', type=Path, default=None)
    a.add_argument('--checkpoints', nargs='+', required=True)
    a.add_argument('--out', type=Path, default=None)
    args = a.parse_args()
    root = args.root.resolve()
    data = load_validation(args.release or root / 'release/SHARP_MASTER_V2')

    print(f'{len(data["state"]):,} validation rows\n')
    print(f'{"checkpoint":34s} {"deploy bal":>10s} {"phys bal":>9s} '
          f'{"gap":>7s} {"dim rec":>8s} {"nec.shed":>9s}')
    rows = {}
    for relative in args.checkpoints:
        path = root / relative if not Path(relative).is_absolute() else Path(relative)
        if not path.exists():
            print(f'{relative:34s} MISSING')
            continue
        r = score(data, path)
        rows[str(relative)] = r
        d, ph = r['deployment'], r['physical']
        print(f'{path.parent.name[:34]:34s} {d["balanced_accuracy"]:10.4f} '
              f'{ph["balanced_accuracy"]:9.4f} '
              f'{ph["balanced_accuracy"] - d["balanced_accuracy"]:+7.4f} '
              f'{d["recall_by_level"]["reduced"]:8.4f} '
              f'{d["necessity_shed_while_entitled"]:9d}')

    print('\nThe deployment column is the one that describes what the Pi will do.')
    if args.out:
        args.out.write_text(json.dumps({
            'status': 'SCORED_UNDER_BOTH_MASKS',
            'note': ('Physical-mask accuracy is inflated: it credits choosing '
                     'actions the deployment mask forbids. Quote the '
                     'deployment column.'),
            'split': 'validation',
            'test_split_used': False,
            'results': rows,
        }, indent=2), encoding='utf-8')
        print(f'Output: {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
