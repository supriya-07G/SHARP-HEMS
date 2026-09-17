"""Build the Raspberry Pi handover bundle for any checkpoint, locally.

Until now the bundle could only be produced inside the Kaggle notebook, because
that is where the golden vector was written. That left two problems:

  * the bundle could not be rebuilt on this machine at all, and
  * a checkpoint trained by any other script had no golden vector, so it could
    never pass the full validation gates however well it controlled.

This reproduces the notebook's export exactly - the same slot ordering, the same
physical mask, the same asymmetric deployment mask - against the release on
disk. It writes:

    sharp_policy.npz      weights plus the normalisation the Pi needs
    golden_vector.json    the boot assertion
    training_report.json  provenance

and leaves the hand-written files in the bundle (run_policy.py,
verify_integration.py, oled_display.py, README.md) untouched.

The slot ordering is the thing to be careful about. Device features attach to
branches by device_id ascending within household; get it wrong and every
appliance is wired to the wrong branch, which does not crash - it returns
confident nonsense while the relays click.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

N_BRANCHES = 28
N_LEVELS = 3                # 0 = OFF (shed), 1 = ON (full), 2 = REDUCED (dim)
DEVICE_FEATURES = 10
GLOBAL_FEATURES = 25
PREFERRED_SERVICE = 6
REMAINING_HOURS = 0

IST = timezone(timedelta(hours=5, minutes=30))


def forward(p, x):
    """Dueling forward pass. Must match run_policy.py on the Pi, byte for byte."""
    h = np.maximum(0, x @ p['w'] + p['b'])
    advantage = (h @ p['a'] + p['ab']).reshape(-1, N_BRANCHES, N_LEVELS)
    value = (h @ p['v'] + p['vb'])[:, :, None]
    return value + advantage - advantage.mean(2, keepdims=True)


def build(root: Path, checkpoint: Path, bundle: Path, release: Path) -> int:
    weights = np.load(checkpoint, allow_pickle=False)
    for key in ['w', 'b', 'v', 'vb', 'a', 'ab', 'mean', 'sd']:
        if key not in weights.files:
            raise SystemExit(f'{checkpoint.name} is missing {key!r}')
    p = {k: weights[k] for k in ['w', 'b', 'v', 'vb', 'a', 'ab']}
    mean, sd = weights['mean'], weights['sd']

    devices = pd.read_parquet(
        release / 'simulator_inputs/device_power_models.parquet',
        columns=['template_id', 'device_id', 'appliance_type',
                 'is_necessity', 'supports_reduced'])
    devices = devices.sort_values(['template_id', 'device_id'])
    devices['slot'] = devices.groupby('template_id').cumcount()
    if devices.slot.max() >= N_BRANCHES:
        raise SystemExit('A household has more devices than there are slots')

    supports_reduced = {(t, s): bool(v) for t, s, v in
                        zip(devices.template_id, devices.slot, devices.supports_reduced)}
    is_necessity = {(t, s): bool(v) for t, s, v in
                    zip(devices.template_id, devices.slot, devices.is_necessity)}

    frame = pd.read_parquet(release / 'rl_transitions/splits/validation.parquet')
    state = np.stack(frame.state.to_numpy()).astype(np.float32)
    present = np.stack(frame.device_present.to_numpy()).astype(np.float32)
    household = frame.household_id.to_numpy()

    row = 0                      # the first validation row, as the notebook uses
    h = household[row]
    normalised = ((state[row:row + 1] - mean) / sd).astype(np.float32)
    q = forward(p, normalised)[0]

    # Physical mask: level 2 only where the appliance can actually dim.
    legal = np.ones((N_BRANCHES, N_LEVELS), dtype=bool)
    for slot in range(N_BRANCHES):
        legal[slot, 2] = supports_reduced.get((h, slot), False)

    necessity = np.array([is_necessity.get((h, s), False) for s in range(N_BRANCHES)])
    offset = np.arange(N_BRANCHES) * DEVICE_FEATURES + GLOBAL_FEATURES
    wanted = ((state[row][offset + PREFERRED_SERVICE] > 0)
              & (state[row][offset + REMAINING_HOURS] > 0))
    entitled = necessity & wanted

    # The deployment mask. The two rules are NOT symmetric:
    #   a critical load is never DIMMED, ever, whether or not it is wanted;
    #   a critical load is never SHED while the occupant is asking for it.
    deployment = legal.copy()
    deployment[:, 2] &= ~necessity
    deployment[:, 0] &= ~entitled

    live = present[row] > 0
    greedy = np.argmax(np.where(live[:, None] & deployment, q, -np.inf), axis=1)

    bundle.mkdir(parents=True, exist_ok=True)
    out_weights = bundle / 'sharp_policy.npz'
    np.savez(out_weights, **{k: weights[k] for k in weights.files})

    reloaded = np.load(out_weights, allow_pickle=False)
    for key in ['w', 'b', 'v', 'vb', 'a', 'ab']:
        if not np.array_equal(reloaded[key], p[key]):
            raise SystemExit(f'Export mismatch on {key}')
    if not np.allclose(forward({k: reloaded[k] for k in p}, normalised), q, atol=1e-10):
        raise SystemExit('Reloaded forward pass does not match')

    golden = {
        'state': normalised[0].tolist(),
        'expected_q': q.tolist(),
        'expected_greedy_action': greedy.tolist(),
        'device_present': present[row].astype(int).tolist(),
        'legal_levels': deployment.astype(int).tolist(),
        'supports_reduced': legal[:, 2].astype(int).tolist(),
        'is_necessity': necessity.astype(int).tolist(),
        'occupant_wants_it': entitled.astype(int).tolist(),
        'policy_rule': (
            'A fan, light or fridge the occupant is using is never shed and '
            'never dimmed - its only legal level is 1. One the occupant is not '
            'asking for may be off; protecting essential service does not mean '
            'running every fan around the clock.'),
        'how_to_check': [
            'Load sharp_policy.npz and read mean and sd from it.',
            'Normalise your state vector: (state - mean) / sd.',
            'Run the dueling forward pass; compare against expected_q.',
            'Mask to legal_levels AND device_present, then argmax.',
            'Compare against expected_greedy_action.',
            'If any comparison fails, REFUSE TO RUN. A wrong policy is worse '
            'than no policy.',
        ],
        'note': ('Assert this on the Pi at boot, before accepting any command. '
                 'Equality proves the state builder, the weights and the mask '
                 'all agree with the machine that trained them.'),
    }
    (bundle / 'golden_vector.json').write_text(
        json.dumps(golden, indent=2), encoding='utf-8')

    report = {
        'status': 'HANDOVER_BUNDLE_BUILT_LOCALLY',
        'source_checkpoint': str(checkpoint.relative_to(root)
                                 if checkpoint.is_relative_to(root) else checkpoint),
        'built_at': datetime.now(IST).isoformat(),
        'policy_version': str(weights['policy_version']) if 'policy_version'
                          in weights.files else 'unknown',
        'trained_at': str(weights['trained_at']) if 'trained_at'
                      in weights.files else 'unknown',
        'feature_count': int(mean.shape[0]),
        'n_branches': N_BRANCHES,
        'n_levels': N_LEVELS,
        'parameter_count': int(sum(v.size for v in p.values())),
        'golden_vector_row': int(row),
        'golden_vector_household': str(h),
        'export_verified': True,
        'test_split_used': False,
        'approved_for_deployment': False,
    }
    (bundle / 'training_report.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')

    size_kb = out_weights.stat().st_size / 1024
    print(f'checkpoint      {checkpoint}')
    print(f'bundle          {bundle}')
    print(f'parameters      {report["parameter_count"]:,} ({size_kb:.0f} KB)')
    print(f'golden vector   household {h}, row {row}')
    print(f'  devices live  {int(live.sum())} of {N_BRANCHES}')
    print(f'  necessity     {int(necessity.sum())}, of which entitled now '
          f'{int(entitled.sum())}')
    print(f'  greedy levels ' + ''.join(str(int(g)) for g in greedy))
    print('\nWrote sharp_policy.npz, golden_vector.json, training_report.json')
    return 0


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    a.add_argument('--checkpoint', type=Path, required=True)
    a.add_argument('--bundle', type=Path, default=None)
    a.add_argument('--release', type=Path, default=None)
    args = a.parse_args()
    root = args.root.resolve()
    raise SystemExit(build(
        root,
        args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint,
        args.bundle or root / 'handover/sharp_rl_v1',
        args.release or root / 'release/SHARP_MASTER_V2'))
