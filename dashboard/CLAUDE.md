@AGENTS.md

# SHARP dashboard — read before editing

## `lib/contracts.ts` is FROZEN

The Pi, the rig and this app must agree on these names and values. Changing a
field here without changing the Pi breaks the system **silently** — nothing
throws, the UI just renders wrong state.

This has already happened once. A refactor deleted `occupant_wants`,
`peak_locked_out`, the frozen appliance ids and the closed `RejectedReason` set
because they looked redundant. They are not. `lib/contracts.test.ts` now fails
if they go again — **run `npm test` before you commit.**

### Fields that look redundant and are not

| Field | Why it exists |
|---|---|
| `occupant_wants` | Protection is **conditional**. `is_necessity` alone is not enough — see the rule below. |
| `peak_locked_out` | Without it the UI leaves "turn on" enabled during a grid peak, the Pi refuses, and nothing visibly happens. |
| `RejectedReason` | A closed set. The Pi sends nothing else. Rendering a raw code like `GRID_PEAK` to a resident is a bug. |
| `APPLIANCE_IDS` | A typo in an id is a silent failure — the appliance simply never updates. |

## Three rules that carry the project

**1. A critical appliance the occupant is using has NO off control.** Not
greyed, not disabled — **absent**. No such action exists anywhere in the system.

**2. But the resident may always switch off their own appliance.** The rule is
`is_necessity && occupant_wants`, never `is_necessity` alone. The shield
protects essential service from the **controller**, not from the person who
lives there. A fridge at 3am that nobody is asking for may be switched off.

**3. A refusal is evidence, not an error.** When the shield refuses something,
render the reason in words from `REJECTION_TEXT`.

## Vocabulary

The idea book defines four load classes: **Critical**, **Thermostatic**,
**Deferrable**, **Interruptible**. Do not invent synonyms. `critical` is a
*permission*; the other three are *dynamics*. A refrigerator is both critical
and thermostatic, which is not a contradiction.

## Honesty rules the UI must keep

- Appliance wattages are **simulated**. No meter is fitted. Say so wherever they
  are shown.
- `measured_w` is `null` in this build. Never put a simulated number there, or a
  stuck relay becomes invisible.
- **Stale data must not look live.** The age indicator is driven by message
  timestamps, not socket state.
- Nothing dims in this build. Two states, not three.

## Demo timing

The measured grid peak is **08:00–17:00**; severity is exactly **0.000** after
18:00. Household load peaks at 19:00 — a different event. Any demo built around
an evening peak will never light the badge. **Run the demo at midday.**

## Before committing

```bash
npm test          # contract guard rails
npx tsc --noEmit  # types
npm run build     # it must compile
```
