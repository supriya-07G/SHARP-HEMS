/**
 * Guard rails for lib/contracts.ts.
 *
 * This file exists because the contract was silently rewritten once already:
 * `occupant_wants`, `peak_locked_out`, the frozen appliance ids and the closed
 * RejectedReason set were all deleted in a refactor. Nothing threw. The UI
 * simply stopped being able to tell "the resident is using this fan" from "this
 * fan is a critical load", and stopped being able to grey out a luxury load the
 * grid has locked.
 *
 * These are not style tests. Each one encodes a rule the project lead set, and
 * a failure here means the deployed dashboard would misrepresent what the
 * hardware does.
 *
 *     npm test
 */

import { describe, it, expect } from 'vitest';
import {
  APPLIANCE_IDS,
  ApplianceState,
  REJECTION_TEXT,
  RejectedReason,
  canShowOffControl,
  homesNotBlackedOut,
  overrideAvailable,
} from './contracts';

function appliance(over: Partial<ApplianceState> = {}): ApplianceState {
  return {
    appliance_id: 'ceiling_fan_01',
    appliance_type: 'ceiling_fan',
    service_class: 'critical',
    is_necessity: true,
    supports_reduced: false,
    level: 1,
    occupant_wants: true,
    peak_locked_out: false,
    power_15min_mean_w: 60,
    measured_w: null,
    gpio_state: 1,
    actuation_verified: true,
    remaining_service_hours: 2.5,
    ...over,
  };
}

describe('the ten appliance ids are frozen', () => {
  it('has exactly ten, matching the hardware spec', () => {
    expect(APPLIANCE_IDS).toHaveLength(10);
    expect(APPLIANCE_IDS).toContain('ceiling_fan_01');
    expect(APPLIANCE_IDS).toContain('ev_charger_01');
  });
});

describe('a critical load in use offers no off control', () => {
  it('hides the control when the occupant is using it', () => {
    expect(canShowOffControl(appliance())).toBe(false);
  });

  // The rule is CONDITIONAL, and this is the half that was lost. The resident
  // may always switch off their own appliance; the shield protects essential
  // service from the controller, not from the person who lives there.
  it('offers it when the occupant is NOT asking for it', () => {
    expect(canShowOffControl(appliance({ occupant_wants: false }))).toBe(true);
  });

  it('offers it on a non-critical load', () => {
    expect(
      canShowOffControl(
        appliance({ is_necessity: false, service_class: 'interruptible' }),
      ),
    ).toBe(true);
  });
});

describe('peak lockout is visible, never silent', () => {
  // Without this the UI leaves "turn on" enabled, the Pi refuses, and nothing
  // happens on screen - the worst failure mode on a demo.
  it('disables the control and gives a reason during a peak', () => {
    const r = overrideAvailable(
      appliance({ is_necessity: false, peak_locked_out: true }),
      true,
    );
    expect(r.enabled).toBe(false);
    expect(r.reason).toBe(REJECTION_TEXT.peak_lockout);
  });

  it('disables everything when the feed is not live', () => {
    expect(overrideAvailable(appliance({ is_necessity: false }), false).enabled)
      .toBe(false);
  });

  it('allows a normal override when live and unlocked', () => {
    expect(overrideAvailable(appliance({ is_necessity: false }), true).enabled)
      .toBe(true);
  });
});

describe('every refusal reason has human text', () => {
  const reasons: RejectedReason[] = [
    'necessity_mask', 'compressor_protection', 'cycle_active',
    'min_on_steps', 'min_off_steps', 'command_expired',
    'level_not_supported', 'peak_lockout', 'watchdog_hold',
  ];

  it('covers the closed set, so no refusal renders as a raw code', () => {
    for (const reason of reasons) {
      expect(REJECTION_TEXT[reason], reason).toBeTruthy();
      expect(REJECTION_TEXT[reason]).not.toMatch(/_/);
    }
  });
});

describe('the equity framing survives', () => {
  it('states peak reduction as homes not blacked out', () => {
    expect(homesNotBlackedOut(8.5)).toBe(
      'equivalent to 8.5 homes in 100 not blacked out',
    );
  });
});
