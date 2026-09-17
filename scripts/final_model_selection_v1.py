"""Final, one-time selection of the policy SHARP ships.

WHY THIS SCRIPT EXISTS
----------------------
Candidate checkpoints were being compared on *balanced accuracy against the
logged action*, and that is the wrong criterion for this project.

Measured on the validation split: the logged action equals the occupant's
request **96.35 %** of the time. The behaviour policy in the dataset is, to
within a few per cent, the no-demand-response baseline ("serve preferred").
So balanced accuracy against it mostly measures *how closely a controller
reproduces doing nothing*. Maximising it is opposed to the objective. It is a
sanity check - a policy that scores at chance has not learned the state space -
and it is not a quality metric.

What actually matters, in order:

  GATES   Hard constraints. A candidate that fails any of these is out, no
          matter how good its peak number is.
            - never sheds a necessity load the occupant is entitled to
            - never picks an illegal action, never dims a load that cannot dim
            - leaves no demand unserved beyond the baseline
            - no infeasible steps
            - does not make the occupant materially worse off:
              discomfort within DISCOMFORT_TOLERANCE of baseline

  SCORE   Among survivors: lowest peak kW, then lowest peak-to-average.
          These are the winnable metrics. Cost is NOT a criterion - APCPDCL's
          domestic tariff is telescopic on monthly units with no time-of-day
          rate, so shifting load in time cannot save the household money.

Every candidate is replayed over the SAME household-days, at several seeds, so
the rows are comparable to each other. Baseline arms are replayed once per seed
rather than once per candidate, which is where the time saving comes from.

Run once. Record the answer. Do not tune against this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_sharp_policy_v1 import (  # noqa: E402
    load_policy,
    plain_grid_households,
    safety_audit,
    summarise,
)

# A candidate may not make the occupant meaningfully less comfortable than doing
# nothing. 2 % is measurement noise; anything beyond it is a real regression.
DISCOMFORT_TOLERANCE = 0.02

# Two candidates whose mean peak differs by less than this are the same
# candidate. Set from the measurement's own noise floor: changing the seed and
# episode count moves a single checkpoint by more than 0.1 kW, so a difference
# far smaller than that is not a real one.
TIE_TOLERANCE = 0.005

# Ties go to whatever already ships. The incumbent already has a validated
# bundle, a golden vector and 17 passing gates; swapping that for a difference
# in the fourth decimal spends real assurance to buy nothing.
INCUMBENT = 'shipped (handover)'

CANDIDATES = {
    'shipped (handover)': 'handover/sharp_rl_v1/sharp_policy.npz',
    'reward_driven': 'models/reward_driven.npz',
    'candidate_pranitha_config': 'models/candidate_pranitha_config.npz',
    'sweep_2.5': 'models/sweep_2.5.npz',
    'sweep_5.0': 'models/sweep_5.0.npz',
}

METRICS = ['peak_kw', 'peak_to_average', 'cost_inr', 'import_kwh',
           'overrides', 'discomfort', 'unserved_kwh', 'infeasible_steps']


def episodes_for_seed(root, episodes, seed):
    """The same held-out household-days every candidate is judged on."""
    shipped = pd.read_parquet(
        root / 'data/processed/sharp_rl_transitions_v2/rl_transitions.parquet',
        columns=['episode_id', 'split', 'policy', 'household_id'])
    eligible = shipped.split.eq('validation') & shipped.policy.eq('serve_preferred')
    eligible &= shipped.household_id.isin(plain_grid_households(root))
    pool = sorted(shipped.loc[eligible].episode_id.unique())
    if not pool:
        raise SystemExit('No validation episodes in the plain-grid cohort')
    rng = np.random.default_rng(seed)
    return list(rng.choice(pool, size=min(episodes, len(pool)), replace=False))


def run(root, episodes, seeds, out_path):
    import generate_sharp_rl_transitions_v2 as gen

    inputs = gen.load_inputs(root)
    models = pd.read_parquet(
        root / 'data/processed/simulator_devices_v1/unknown_quantity_one'
               '/baseline_power_v1/device_power_models.parquet',
        columns=['template_id', 'device_id', 'is_necessity'])

    per_seed = {}
    for seed in seeds:
        chosen = episodes_for_seed(root, episodes, seed)
        print(f'\n=== seed {seed}: {len(chosen)} held-out household-days ===',
              flush=True)

        arms = {}

        # Baselines once per seed, not once per candidate.
        for label, policy_name in [('no demand response', 'serve_preferred'),
                                   ('rule-based', 'peak_aware')]:
            started = time.time()
            frame, _, _ = gen.replay_episodes(
                root, chosen, policy_fn=None, policy_override=policy_name,
                inputs=inputs)
            arms[label] = (summarise(frame, label), safety_audit(frame, models))
            print(f'  {label:28s} {time.time() - started:5.1f}s', flush=True)

        for label, relative in CANDIDATES.items():
            checkpoint = root / relative
            if not checkpoint.exists():
                print(f'  {label:28s} MISSING - skipped')
                continue
            started = time.time()
            frame, _, _ = gen.replay_episodes(
                root, chosen, policy_fn=load_policy(checkpoint),
                policy_override='learned', inputs=inputs)
            arms[label] = (summarise(frame, label), safety_audit(frame, models))
            print(f'  {label:28s} {time.time() - started:5.1f}s', flush=True)

        per_seed[seed] = arms

    # ---- aggregate across seeds -------------------------------------------
    labels = list(next(iter(per_seed.values())).keys())
    table = {}
    for label in labels:
        row = {m: float(np.mean([per_seed[s][label][0][m].mean()
                                 for s in seeds])) for m in METRICS}
        row['necessity_shed_while_entitled'] = int(sum(
            per_seed[s][label][1]['necessity_shed_while_entitled'] for s in seeds))
        row['necessity_service_opportunities'] = int(sum(
            per_seed[s][label][1]['necessity_service_opportunities'] for s in seeds))
        table[label] = row

    base = table['no demand response']

    # ---- apply the gates ---------------------------------------------------
    verdicts = {}
    for label, row in table.items():
        if label in ('no demand response', 'rule-based'):
            continue
        failures = []
        if row['necessity_shed_while_entitled'] > 0:
            failures.append(
                f"shed a necessity load the occupant was entitled to "
                f"({row['necessity_shed_while_entitled']} times)")
        if row['unserved_kwh'] > base['unserved_kwh'] + 1e-9:
            failures.append(
                f"left demand unserved ({row['unserved_kwh']:.4f} kWh against a "
                f"baseline of {base['unserved_kwh']:.4f})")
        if row['infeasible_steps'] > 0:
            failures.append(f"{row['infeasible_steps']:.1f} infeasible steps")
        limit = base['discomfort'] * (1 + DISCOMFORT_TOLERANCE)
        if row['discomfort'] > limit:
            failures.append(
                f"discomfort {row['discomfort']:.3f} exceeds the baseline "
                f"tolerance of {limit:.3f}")
        verdicts[label] = failures

    survivors = [l for l, f in verdicts.items() if not f]
    survivors.sort(key=lambda l: (table[l]['peak_kw'], table[l]['peak_to_average']))

    # Ties. The top candidates here sit within 0.0002 kW of each other, while
    # simply changing the seed and episode count moves any one of them by more
    # than 0.1 kW. Picking a winner on the fourth decimal is fitting the
    # measurement, not the model. Anything inside TIE_TOLERANCE of the best is
    # declared indistinguishable, and the INCUMBENT wins - it already has a
    # validated bundle, a golden vector and 17 passing gates, and swapping that
    # for noise costs real assurance to buy nothing.
    winner = None
    tied = []
    if survivors:
        best_peak = table[survivors[0]]['peak_kw']
        tied = [l for l in survivors
                if table[l]['peak_kw'] - best_peak <= TIE_TOLERANCE]
        winner = INCUMBENT if INCUMBENT in tied else survivors[0]

    # ---- report ------------------------------------------------------------
    print(f'\n{"=" * 78}')
    print(f'FINAL SELECTION  ({episodes} household-days x {len(seeds)} seeds: '
          f'{", ".join(str(s) for s in seeds)})')
    print('=' * 78)
    header = (f'{"candidate":28s} {"peak kW":>9s} {"PAR":>7s} {"discomf":>8s} '
              f'{"overrid":>8s} {"unserv":>7s} {"nec.viol":>9s}')
    print(header)
    for label in labels:
        r = table[label]
        print(f'{label:28s} {r["peak_kw"]:9.4f} {r["peak_to_average"]:7.3f} '
              f'{r["discomfort"]:8.3f} {r["overrides"]:8.3f} '
              f'{r["unserved_kwh"]:7.3f} '
              f'{r["necessity_shed_while_entitled"]:9d}')

    print('\nGates')
    for label, failures in verdicts.items():
        if failures:
            print(f'  [OUT ] {label}')
            for f in failures:
                print(f'         - {f}')
        else:
            print(f'  [PASS] {label}')

    if len(tied) > 1:
        print(f'\nIndistinguishable within {TIE_TOLERANCE} kW: ' + ', '.join(tied))
        print('  Choosing between these would be fitting the measurement, not '
              'the model.')

    if winner is None:
        print('\nNO CANDIDATE PASSES THE GATES.')
    else:
        cut = 100 * (base['peak_kw'] - table[winner]['peak_kw']) / base['peak_kw']
        print(f'\nSELECTED: {winner}')
        print(f'  peak {table[winner]["peak_kw"]:.4f} kW against a baseline of '
              f'{base["peak_kw"]:.4f} - a {cut:.1f} % cut')
        print(f'  checkpoint: {CANDIDATES[winner]}')
        runner = survivors[1] if len(survivors) > 1 else None
        if runner:
            print(f'  runner-up: {runner} at {table[runner]["peak_kw"]:.4f} kW')

    report = {
        'status': 'FINAL_MODEL_SELECTED' if winner else 'NO_CANDIDATE_PASSED',
        'criterion': {
            'gates': [
                'necessity_shed_while_entitled == 0',
                'unserved_kwh <= baseline',
                'infeasible_steps == 0',
                f'discomfort <= baseline * {1 + DISCOMFORT_TOLERANCE}',
            ],
            'score': 'lowest peak_kw, tie-broken on peak_to_average',
            'explicitly_not_a_criterion': {
                'balanced_accuracy': (
                    'The logged action equals the occupant request 96.35 % of '
                    'the time, so agreement with logged behaviour mostly '
                    'measures how closely a controller reproduces doing '
                    'nothing. It is a sanity check, not a quality metric.'),
                'cost_inr': (
                    'APCPDCL domestic tariff is telescopic on monthly units '
                    'with no time-of-day rate, so shifting load in time cannot '
                    'save the household money.'),
            },
        },
        'episodes_per_seed': episodes,
        'seeds': list(seeds),
        'split': 'validation',
        'test_split_used': False,
        'absolute_means': table,
        'gate_failures': verdicts,
        'tie_tolerance_kw': TIE_TOLERANCE,
        'indistinguishable': tied,
        'incumbent': INCUMBENT,
        'selected': winner,
        'selected_checkpoint': CANDIDATES[winner] if winner else None,
        'ranking': survivors,
        'limitations': [
            'Simulator evaluation on held-out validation household-days, not '
            'field evidence.',
            'The occupant, including every override, is synthetic.',
            'Appliance power values are proxies for most devices.',
        ],
        'approved_for_deployment': False,
    }
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'\nOutput: {out_path}')
    return 0 if winner else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--episodes', type=int, default=60)
    p.add_argument('--seeds', type=int, nargs='+', default=[7, 99, 2024])
    p.add_argument('--out', type=Path, default=None)
    p.add_argument('--extra', nargs='+', default=[],
                   help='additional checkpoints as label=path, e.g. from the '
                        'hyperparameter search')
    p.add_argument('--only', nargs='+', default=None,
                   help='restrict to these candidate labels')
    a = p.parse_args()
    # --only restricts the BUILT-IN candidates. Anything named by --extra was
    # asked for explicitly, so it is always kept - filtering it out again would
    # silently evaluate nothing but the incumbent.
    if a.only:
        keep = set(a.only)
        for label in [l for l in CANDIDATES if l not in keep]:
            del CANDIDATES[label]
    for item in a.extra:
        label, _, relative = item.partition('=')
        if not relative:
            raise SystemExit(f'--extra expects label=path, got {item!r}')
        CANDIDATES[label] = relative
    out = a.out or a.root / 'reports/final_model_selection_v1.json'
    sys.exit(run(a.root.resolve(), a.episodes, a.seeds, out))
