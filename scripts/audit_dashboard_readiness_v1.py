"""What is actually stopping the dashboard from being built?

Written because "what's blocking us" kept being answered from memory. Each check
either finds the thing on disk or it does not. A BLOCKER is something no amount
of UI work can proceed past; a GAP is work that is simply not done yet.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / 'dashboard'

results = []


def record(kind, name, ok, detail):
    results.append((kind, name, ok, detail))


def read(path):
    p = ROOT / path
    return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''


# --- 1. Do the two appliance registries agree? -----------------------------
guide = read('docs/INTEGRATION_GUIDE.md')
spec = read('docs/HARDWARE_PROTOTYPE_SPEC.md')
guide_ids = set(re.findall(r'`([a-z_]+_\d{2})`', guide))
contracts = read('dashboard/lib/contracts.ts')
frozen = set(re.findall(r"^\s*'([a-z_]+_\d{2})',", contracts, re.M))
mock_ids = set(re.findall(r"appliance_id: '([a-z_0-9]+)'", read('dashboard/lib/mockState.ts')))

record('BLOCKER', 'appliance registry agrees across docs and code',
       bool(frozen) and bool(mock_ids) and frozen == mock_ids,
       f'contracts has {len(frozen)}, mock has {len(mock_ids)}, '
       f'integration guide has {len(guide_ids)}; '
       f'mock-only: {sorted(mock_ids - frozen) or "none"}; '
       f'contract-only: {sorted(frozen - mock_ids) or "none"}')

# --- 2. Is there any live data source at all? ------------------------------
publisher = list(ROOT.glob('scripts/*replay*publish*.py')) + \
            list(ROOT.glob('scripts/*publish*.py'))
record('BLOCKER', 'replay publisher exists (the only live data source)',
       bool(publisher),
       f'found {[p.name for p in publisher]}' if publisher
       else 'no publisher; the dashboard can only ever run on mock data')

# --- 3. Can the resident role be told apart from the others? ---------------
# Decision: NO authentication for the demo. A visible role switcher stands in
# for it, so all three views can be shown in one sitting. Real auth is required
# before this is ever exposed beyond a demo - a grid controller sheds load in
# every home that listens, and that must not be a URL anyone can visit.
role_switcher = bool(re.search(r'role', read('dashboard/lib/roles.ts')
                               or read('dashboard/components/RoleSwitcher.tsx'), re.I))
record('GAP', 'role switcher (stands in for auth, by decision)',
       role_switcher, 'no roles.ts or RoleSwitcher.tsx yet')

# --- 4. Routes for the three roles ----------------------------------------
app = DASH / 'app'
routes = sorted(p.parent.name for p in app.glob('*/page.tsx')) if app.exists() else []
record('GAP', 'a route per role (resident / grid / technical)',
       len(routes) >= 2, f'routes found: {routes or ["/ only"]}')

# --- 5. Billing: is the tariff actually available to compute a bill? -------
tariffs = list((ROOT / 'configs' / 'tariffs').glob('*.json')) \
    if (ROOT / 'configs' / 'tariffs').exists() else []
record('GAP', 'tariff configuration available for the billing simulator',
       bool(tariffs), f'{[p.name for p in tariffs]}' if tariffs else 'none found')

billing_ui = [p.name for p in (DASH / 'components').glob('*')
              if re.search(r'bill|tariff|cost', p.name, re.I)] \
    if (DASH / 'components').exists() else []
record('GAP', 'billing simulator UI (idea book 44-47, D11)',
       bool(billing_ui), f'{billing_ui}' if billing_ui else 'no billing component')

# --- 6. Credits, for pay-to-keep ------------------------------------------
credit_hits = re.findall(r'credit', contracts, re.I)
record('GAP', 'credits modelled in the contract (pay-to-keep during a peak)',
       bool(credit_hits), 'no credit field in contracts.ts')

# --- 7. Override event: the training label --------------------------------
has_override_event = 'override_event' in contracts or 'OverrideRequest' in contracts
record('GAP', 'override event shape exists (the reward-model training label)',
       has_override_event, 'no OverrideRequest / override_event in contracts.ts')

# --- 8. Does the mock cover every state the UI must render? ---------------
mock = read('dashboard/lib/mockState.ts')
states = {'peak active': r'peak_event_active|peak_locked_out',
          'outage': r'islanded|grid_absent|outage',
          'shed load': r'level: 0',
          'refusal reason': r'shield_reasons|rejected_reason|shed_reason'}
missing = [k for k, pat in states.items() if not re.search(pat, mock)]
record('GAP', 'mock covers peak / outage / shed / refusal',
       not missing, f'missing: {missing}' if missing else 'all four present')

# --- 9. Weather, which the spec says the dashboard shows -------------------
record('GAP', 'weather adapter (idea book 39, keys server-side)',
       bool(list(ROOT.glob('scripts/*weather*adapter*')) +
            list(DASH.glob('app/api/weather/**/*'))),
       'no weather adapter on either side')

# --- 10. Guard rails ------------------------------------------------------
record('OK', 'contract guard tests',
       (DASH / 'lib' / 'contracts.test.ts').exists(),
       'contracts.test.ts present')

# --- report ---------------------------------------------------------------
width = 58
print('\nDASHBOARD READINESS\n' + '=' * (width + 22))
blockers = gaps = 0
for kind, name, ok, detail in results:
    if ok:
        mark = '[ OK     ]'
    elif kind == 'BLOCKER':
        mark, = ('[ BLOCKER]',)
        blockers += 1
    else:
        mark = '[ GAP    ]'
        gaps += 1
    print(f'{mark} {name:{width}s}')
    if not ok:
        print(f'{"":11s}{detail}')

print('=' * (width + 22))
print(f'{blockers} blocker(s), {gaps} gap(s)')
print('\nBLOCKER = no UI work can proceed past it.')
print('GAP     = work not done yet, but nothing is stopping it.')
sys.exit(1 if blockers else 0)
