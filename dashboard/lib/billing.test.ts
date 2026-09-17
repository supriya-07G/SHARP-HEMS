/**
 * The billing maths, checked by hand against the APCPDCL FY2025-26 slabs.
 *
 * The failure this guards against is charging every unit at the top slab's
 * rate. That is not a small error: at 250 units it overstates the bill by more
 * than four hundred rupees, and it would be invisible without a test because
 * the number still looks plausible.
 */

import { describe, it, expect } from 'vitest';
import {
  TARIFF, computeBill, energyCharge, marginalRate, compareScenarios,
} from './billing';

describe('telescopic slabs', () => {
  it('bills the first 30 units at 1.90', () => {
    // 30 x 1.90 = 57.00
    expect(energyCharge(30).total).toBeCloseTo(57.0, 2);
  });

  it('splits across slabs rather than using one rate', () => {
    // 100 units = 30@1.90 + 45@3.00 + 25@4.50 = 57 + 135 + 112.5 = 304.50
    expect(energyCharge(100).total).toBeCloseTo(304.5, 2);
  });

  it('is NOT the flat top-slab calculation', () => {
    // The bug being guarded: 100 x 4.50 = 450, which is 145.50 too much.
    expect(energyCharge(100).total).not.toBeCloseTo(450, 0);
  });

  it('handles the open-ended top slab', () => {
    // 500 units: 57 + 135 + 225 + 600 + 1531.25 + 975 = 3523.25
    //  30@1.90=57, 45@3.00=135, 50@4.50=225, 100@6.00=600,
    // 175@8.75=1531.25, 100@9.75=975
    expect(energyCharge(500).total).toBeCloseTo(3523.25, 2);
  });

  it('charges nothing for no units', () => {
    expect(energyCharge(0).total).toBe(0);
    expect(energyCharge(-5).total).toBe(0);
  });

  it('every line stays inside its own slab', () => {
    const { lines } = energyCharge(500);
    expect(lines).toHaveLength(TARIFF.slabs.length);
    expect(lines[0].units).toBe(30);
    expect(lines[1].units).toBe(45);
  });
});

describe('marginal rate is what the next unit costs', () => {
  it('reports the slab the household is standing in', () => {
    expect(marginalRate(20).rate).toBe(1.9);
    expect(marginalRate(100).rate).toBe(4.5);
    expect(marginalRate(600).rate).toBe(9.75);
  });
});

describe('a whole bill', () => {
  it('adds fixed and customer charges to the energy charge', () => {
    const bill = computeBill({ units: 100, sanctionedLoadKw: 2 });
    expect(bill.energyCharge).toBeCloseTo(304.5, 2);
    expect(bill.fixedCharge).toBe(20);     // 10/kW x 2 kW
    expect(bill.customerCharge).toBe(45);  // the 76-125 slab
    expect(bill.total).toBeCloseTo(369.5, 2);
  });

  it('applies an opt-out surcharge only when an event was opted out of', () => {
    const none = computeBill({ units: 100, sanctionedLoadKw: 2 });
    const one = computeBill({ units: 100, sanctionedLoadKw: 2, optedOutEvents: 1 });
    expect(none.peakSurcharge).toBe(0);
    expect(one.peakSurcharge).toBeGreaterThan(0);
    expect(one.total).toBeGreaterThan(none.total);
  });

  it('credits participation, so a household that never opts out pays less', () => {
    const plain = computeBill({ units: 100, sanctionedLoadKw: 2 });
    const took = computeBill({
      units: 100, sanctionedLoadKw: 2, participatedEvents: 3,
    });
    expect(took.total).toBeLessThan(plain.total);
  });
});

describe('the tariff must not drift', () => {
  it('has no domestic time-of-day rate', () => {
    // If this ever flips, every "shift your load and save" claim needs
    // revisiting - today shifting load in time saves the household nothing.
    expect(TARIFF.timeOfDayRates).toBe(false);
  });

  it('excludes the components the order excludes', () => {
    expect(TARIFF.excluded).toContain('electricity duty');
    expect(TARIFF.excluded).toContain('FPPCA');
  });
});

describe('three-scenario comparison', () => {
  it('produces all three and a signed saving', () => {
    const c = compareScenarios(120, 2);
    expect(c.noControl.total).toBeGreaterThan(0);
    expect(c.ruleBased.total).toBeGreaterThan(0);
    expect(c.sharp.total).toBeGreaterThan(0);
    expect(typeof c.savingsVsNoControl).toBe('number');
  });
});
