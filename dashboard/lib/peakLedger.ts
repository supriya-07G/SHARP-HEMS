/**
 * Peak-event billing ledger, built only from what the Pi publishes on
 * home/<house>/grid/warning. A tap in the browser is a request; the Pi's
 * opted_out list is what counts, so the bill never charges for a request the
 * Pi did not register.
 *
 * Events are keyed by warning_started_at, so a retained message redelivered
 * on reconnect merges into the same entry instead of counting twice.
 */

import type { GridWarningPayload } from './mqtt';

export interface PeakLedgerEntry {
  affected: string[];
  optedOut: string[];
  reachedActive: boolean;
  ended: boolean;
}

export type PeakLedger = Record<string, PeakLedgerEntry>;

/** 'household' is this house's own peak with no grid peak. */
export type PeakPhase = 'none' | 'warning' | 'active' | 'household';

export interface GridWarningState {
  phase: PeakPhase;
  /** warning_started_at of the running event, or null. */
  eventKey: string | null;
  severity: number;
  /** Epoch ms at which unrequested flexible loads are shed. */
  shedAtMs: number | null;
  leadTimeSeconds: number;
  affectedLoads: string[];
  optedOut: string[];
}

export const NO_GRID_WARNING: GridWarningState = {
  phase: 'none',
  eventKey: null,
  severity: 0,
  shedAtMs: null,
  leadTimeSeconds: 0,
  affectedLoads: [],
  optedOut: [],
};

export function warningState(w: GridWarningPayload): GridWarningState {
  if (w.action === 'cancel') return NO_GRID_WARNING;
  const shedAt = w.shed_at ? Date.parse(w.shed_at) : NaN;
  return {
    phase: w.action,
    eventKey: w.warning_started_at,
    severity: Number(w.severity ?? 0),
    shedAtMs: Number.isNaN(shedAt) ? null : shedAt,
    leadTimeSeconds: Number(w.lead_time_seconds ?? 0),
    affectedLoads: w.affected_loads ?? [],
    optedOut: w.opted_out ?? [],
  };
}

export function applyWarning(
  ledger: PeakLedger,
  w: GridWarningPayload,
): PeakLedger {
  const key = w.warning_started_at;
  if (!key) return ledger;

  const prev: PeakLedgerEntry = ledger[key] ?? {
    affected: [], optedOut: [], reachedActive: false, ended: false,
  };

  // The Pi only ever adds to opted_out within an event, so union is exact
  // even if messages arrive out of order.
  const optedOut = Array.from(new Set([...prev.optedOut, ...(w.opted_out ?? [])])).sort();
  const affected = Array.from(new Set([...prev.affected, ...(w.affected_loads ?? [])])).sort();

  return {
    ...ledger,
    [key]: {
      affected,
      optedOut,
      // Shedding happened under either kind of peak.
      reachedActive:
        prev.reachedActive || w.action === 'active' || w.action === 'household',
      ended: prev.ended || w.action === 'cancel',
    },
  };
}

/** "YYYY-MM" in IST, matching the prefix of the Pi's IST timestamps. */
export function istMonth(ms: number = Date.now()): string {
  return new Date(ms + 5.5 * 3600 * 1000).toISOString().slice(0, 7);
}

export function ledgerCounts(ledger: PeakLedger, month: string = istMonth()) {
  let optedOutEvents = 0;
  let participatedEvents = 0;

  for (const [key, entry] of Object.entries(ledger)) {
    if (key.slice(0, 7) !== month) continue;
    // Surcharge is per device per event, as the notice quotes it.
    optedOutEvents += entry.optedOut.length;
    // Relief credit is per event the household actually rode through with
    // at least one flexible load paused.
    if (
      entry.ended &&
      entry.reachedActive &&
      entry.affected.some((id) => !entry.optedOut.includes(id))
    ) {
      participatedEvents += 1;
    }
  }

  return { optedOutEvents, participatedEvents };
}
