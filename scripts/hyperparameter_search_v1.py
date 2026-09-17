"""Hyperparameter search for the SHARP policy.

ORIGIN
------
The design is Gudala Padma Pranitha's, from PR #1 (Jadephoenix05): a random
search over the knobs that earlier ablations showed were sensitive, deliberately
EXCLUDING reward-shaping and safety choices - PEAK_WEIGHT, COST_WEIGHT, the
illegal-action penalty - because those are grounded in domain reasoning and are
not free parameters. That judgement was right and is kept.

WHAT CHANGED, AND WHY
---------------------
Her version selects the winner by balanced accuracy. That cannot work here. The
logged action equals the occupant's request 96.35 % of the time, so agreement
with logged behaviour mostly measures how closely a controller reproduces DOING
NOTHING; a search that maximises it walks away from demand response.

An in-notebook proxy for control quality was tried and REJECTED. Scoring the
fraction of discretionary load shed during peaks versus off-peak ranked five
known checkpoints at Spearman -0.900 against the simulator - almost perfectly
inverted. A policy that sheds hard during peaks looks well targeted and simply
gets overridden by the occupant, so no peak is avoided. See
peak_response_proxy_v1.py.

So control quality is NOT scored here. This script does what can be done
honestly offline:

  * trains each trial,
  * applies the hard gates (illegal picks, non-finite loss),
  * keeps balanced accuracy as a SANITY FILTER - a model near chance has not
    learned the state space - never as the objective,
  * exports every surviving candidate,

and then final_model_selection_v1.py ranks the survivors IN THE SIMULATOR,
across several seeds, which is the only place peak reduction is measurable.

Two settings are fixed and not searched, because both were measured and
refuted; her branch had silently reverted them:
    USE_BALANCED_SAMPLING  stays off  (dim recall 0.011 -> 0.015 while costing
                                       six points of OFF recall)
    level weighting        stays min-normalised
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import train_sharp_bdq_v3 as trainer  # noqa: E402

# Pranitha's space, unchanged.
SEARCH_SPACE = {
    'alpha':      [0.5, 1.0, 1.5, 2.0],
    'warm_start': [1000, 2000, 3000],
    'hidden':     [64, 128, 256],
    'lr':         [1e-4, 3e-4, 1e-3],
    'scale':      [5.0, 10.0, 20.0],
}

# The configuration that produced the shipped policy. Trial 0, so the search
# always has the incumbent to beat on equal terms.
DEFAULTS = {'alpha': 1.0, 'warm_start': 2000, 'hidden': 128,
            'lr': 3e-4, 'scale': 10.0}

# Below this the model has not learned the state space - chance is 0.3333.
SANITY_FLOOR = 0.45


def sample(rng):
    return {k: v[int(rng.integers(len(v)))] for k, v in SEARCH_SPACE.items()}


def run(root: Path, trials: int, steps: int, seed: int, out_dir: Path):
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    combos = [('defaults', dict(DEFAULTS))]
    seen = {tuple(sorted(DEFAULTS.items()))}
    while len(combos) < trials:
        combo = sample(rng)
        key = tuple(sorted(combo.items()))
        if key in seen:
            continue
        seen.add(key)
        combos.append((f'trial{len(combos)}', combo))

    results = []
    for label, combo in combos:
        started = time.time()
        print(f'\n--- {label}: {combo} ---', flush=True)
        try:
            report = trainer.fit(
                root, steps=steps, warm_start=combo['warm_start'], batch=256,
                gamma=0.99, scale=combo['scale'], alpha=combo['alpha'],
                lr=combo['lr'], seed=42, hidden=combo['hidden'],
                level_balance=True,        # min-normalised; measured, kept
                filter_imitation=False,    # measured and refuted
                scenarios=['main'], tag=f'hp_{label}')
        except Exception as exc:                      # a trial may diverge
            print(f'  {label} FAILED: {type(exc).__name__}: {exc}')
            results.append({'label': label, **combo, 'status': 'FAILED',
                            'error': f'{type(exc).__name__}: {exc}'})
            continue

        # train_sharp_bdq_v3 calls it 'final'; the notebook calls the same thing
        # 'final_validation'. Accept either, and fail loudly rather than
        # silently scoring every trial zero.
        final = report.get('final') or report.get('final_validation')
        if not final or 'balanced_accuracy' not in final:
            raise KeyError(
                f'{label}: no validation block in the training report '
                f'(keys: {sorted(report)[:12]})')
        balanced = float(final.get('balanced_accuracy', 0.0))
        illegal = int(final.get('illegal_greedy_picks', 0))
        gates = []
        if illegal:
            gates.append(f'{illegal} illegal greedy picks')
        if balanced < SANITY_FLOOR:
            gates.append(f'balanced accuracy {balanced:.4f} below the sanity '
                         f'floor {SANITY_FLOOR}')

        row = {'label': label, **combo,
               'status': 'PASS' if not gates else 'GATED',
               'gate_failures': gates,
               'balanced_accuracy': balanced,
               'td_error_non_terminal': float(final.get('td_error_non_terminal', float('nan'))),
               'illegal_greedy_picks': illegal,
               'parameter_count': int(report.get('parameter_count', 0)),
               'dim_recall': float(final.get('recall_by_level', {}).get('reduced', float('nan'))),
               'checkpoint': f'models/sharp_bdq_v3_hp_{label}/checkpoint.npz',
               'minutes': round((time.time() - started) / 60, 2)}
        results.append(row)
        print(f'  {label}: balanced {balanced:.4f}  illegal {illegal}  '
              f'{row["status"]}  ({row["minutes"]} min)', flush=True)

    passed = [r for r in results if r['status'] == 'PASS']
    passed.sort(key=lambda r: -r['balanced_accuracy'])

    print(f'\n{"=" * 78}\nHYPERPARAMETER SEARCH ({len(results)} trials)\n{"=" * 78}')
    print(f'{"label":10s} {"alpha":>6s} {"warm":>6s} {"hidden":>7s} {"lr":>8s} '
          f'{"scale":>6s} {"balanced":>9s} {"status":>7s}')
    for r in sorted(results, key=lambda r: -r.get('balanced_accuracy', -1)):
        print(f'{r["label"]:10s} {r.get("alpha", 0):6.1f} {r.get("warm_start", 0):6d} '
              f'{r.get("hidden", 0):7d} {r.get("lr", 0):8.4f} {r.get("scale", 0):6.1f} '
              f'{r.get("balanced_accuracy", float("nan")):9.4f} {r["status"]:>7s}')

    incumbent = next((r for r in results if r['label'] == 'defaults'), None)
    print('\nBalanced accuracy is a SANITY FILTER here, not the objective.')
    if incumbent and passed:
        better = [r for r in passed
                  if r['balanced_accuracy'] > incumbent['balanced_accuracy']]
        print(f'  incumbent (defaults): {incumbent["balanced_accuracy"]:.4f}')
        print(f'  trials above it:      {len(better)}')
        print('\nCandidates to carry into the simulator '
              '(final_model_selection_v1.py):')
        for r in passed[:5]:
            print(f'  {r["checkpoint"]}   balanced '
                  f'{r["balanced_accuracy"]:.4f}  dim recall {r["dim_recall"]:.4f}')
        print('\nThe simulator decides. A higher balanced accuracy here is NOT '
              'a better controller.')

    report_path = out_dir / 'hyperparameter_search_v1.json'
    report_path.write_text(json.dumps({
        'status': 'HYPERPARAMETER_SEARCH_COMPLETE',
        'origin': ('Search design by Gudala Padma Pranitha, PR #1. Selection '
                   'objective changed: see the module docstring.'),
        'trials': len(results),
        'steps_per_trial': steps,
        'search_space': {k: list(v) for k, v in SEARCH_SPACE.items()},
        'fixed_not_searched': {
            'use_balanced_sampling': False,
            'level_weight_norm': 'min',
            'reason': 'Both measured and refuted; not free parameters.',
        },
        'sanity_floor': SANITY_FLOOR,
        'selection_note': ('Balanced accuracy is a sanity filter. Control '
                           'quality is decided in the simulator by '
                           'final_model_selection_v1.py.'),
        'results': results,
        'carry_forward': [{'label': r['label'], 'checkpoint': r['checkpoint']}
                          for r in passed[:5]],
        'test_split_used': False,
        'approved_for_deployment': False,
    }, indent=2), encoding='utf-8')
    print(f'\nOutput: {report_path}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--trials', type=int, default=10)
    p.add_argument('--steps', type=int, default=4000)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--out', type=Path, default=None)
    a = p.parse_args()
    root = a.root.resolve()
    raise SystemExit(run(root, a.trials, a.steps, a.seed, a.out or root / 'reports'))
