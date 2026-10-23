import { describe, expect, it } from 'vitest';
import type { GridWarningPayload } from './mqtt';
import {
  applyWarning, istMonth, ledgerCounts, warningState, PeakLedger,
} from './peakLedger';

const AFFECTED = ['air_conditioner_01', 'ev_charger_01', 'television_01'];

function msg(
  action: GridWarningPayload['action'],
  optedOut: string[] = [],
  started = '2026-10-23T12:00:00+05:30',
): GridWarningPayload {
  return {
    schema_version: 'sharp_grid_warning_v1',
    action,
    house_id: 'house_01',
    severity: 0.85,
    warning_started_at: started,
    shed_at: '2026-10-23T12:10:00+05:30',
    lead_time_seconds: 600,
    affected_loads: AFFECTED,
    opted_out: optedOut,
    timestamp_ist: started,
  };
}

function run(...msgs: GridWarningPayload[]): PeakLedger {
  return msgs.reduce(applyWarning, {} as PeakLedger);
}

describe('peak ledger', () => {
  it('counts only opt-outs the Pi registered, once per device per event', () => {
    const ledger = run(
      msg('warning'),
      msg('warning', ['air_conditioner_01']),
      // Retained redelivery after a reconnect must not double count.
      msg('warning', ['air_conditioner_01']),
      msg('active', ['air_conditioner_01']),
    );
    expect(ledgerCounts(ledger, '2026-10').optedOutEvents).toBe(1);
  });

  it('credits participation only when an active event ends with a load paused', () => {
    const rode = run(msg('warning'), msg('active'), msg('cancel'));
    expect(ledgerCounts(rode, '2026-10').participatedEvents).toBe(1);

    const cancelledEarly = run(msg('warning'), msg('cancel'));
    expect(ledgerCounts(cancelledEarly, '2026-10').participatedEvents).toBe(0);

    const keptEverything = run(msg('warning', AFFECTED), msg('active', AFFECTED), msg('cancel', AFFECTED));
    expect(ledgerCounts(keptEverything, '2026-10')).toEqual({
      optedOutEvents: 3, participatedEvents: 0,
    });
  });

  it('scopes counts to the billing month', () => {
    const ledger = run(msg('warning', ['ev_charger_01'], '2026-09-30T12:00:00+05:30'));
    expect(ledgerCounts(ledger, '2026-10').optedOutEvents).toBe(0);
    expect(ledgerCounts(ledger, '2026-09').optedOutEvents).toBe(1);
  });

  it('uses the IST month near midnight UTC', () => {
    // 2026-10-31T20:00Z is 2026-11-01 01:30 IST.
    expect(istMonth(Date.parse('2026-10-31T20:00:00Z'))).toBe('2026-11');
  });

  it('maps a cancel to no warning and a warning to a shed deadline', () => {
    expect(warningState(msg('cancel')).phase).toBe('none');
    const w = warningState(msg('warning'));
    expect(w.phase).toBe('warning');
    expect(w.shedAtMs).toBe(Date.parse('2026-10-23T12:10:00+05:30'));
  });
});
