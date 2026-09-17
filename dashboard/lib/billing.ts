/**
 * The billing simulator. Idea book §44-47.
 *
 * Every number the tariff needs comes from
 * `configs/tariffs/apcpdcl_2025_26_verified_components.json`, which was read
 * off the published APCPDCL RST order for FY2025-26. Do not invent a rate here.
 *
 * THREE RULES THIS FILE EXISTS TO KEEP
 *
 *  1. Telescopic, not flat. Each slab charges only the units that fall inside
 *     it. Charging every unit at the top slab's rate overstates a big month by
 *     hundreds of rupees.
 *
 *  2. Never invent a penalty (§46). A penalty may be modelled only where the
 *     tariff or programme actually defines one. Electricity duty, FPPCA,
 *     true-up and subsidies are EXCLUDED from this order's components, so the
 *     total here is not a full utility bill and says so.
 *
 *  3. There is no domestic time-of-day rate (`time_of_day_rates: false`).
 *     Shifting load in time therefore saves the household NOTHING. Any peak
 *     surcharge shown is a PROPOSAL under the 2023 Rules, never a charge this
 *     DISCOM currently issues.
 */

export interface Slab {
  upper_kwh: number | null;
  energy_inr_kwh: number;
  customer_inr_month: number;
}

/** APCPDCL category I(A) domestic LT, FY2025-26. Verified components only. */
export const TARIFF = {
  id: 'APCPDCL_CAT_IA_LT_FY2025_26_ORDER_COMPONENTS_V1',
  effectiveFrom: '2025-04-01',
  effectiveTo: '2026-03-31',
  category: 'I(A) Domestic LT',
  method: 'telescopic' as const,
  timeOfDayRates: false,
  fixedInrPerKwPerMonth: 10,
  slabs: [
    { upper_kwh: 30, energy_inr_kwh: 1.9, customer_inr_month: 25 },
    { upper_kwh: 75, energy_inr_kwh: 3.0, customer_inr_month: 30 },
    { upper_kwh: 125, energy_inr_kwh: 4.5, customer_inr_month: 45 },
    { upper_kwh: 225, energy_inr_kwh: 6.0, customer_inr_month: 50 },
    { upper_kwh: 400, energy_inr_kwh: 8.75, customer_inr_month: 55 },
    { upper_kwh: null, energy_inr_kwh: 9.75, customer_inr_month: 55 },
  ] as Slab[],
  excluded: [
    'electricity duty', 'FPPCA', 'true-up / true-down',
    'consumer subsidies', 'other recoveries', 'late payment charges',
  ],
} as const;

export interface SlabLine {
  label: string;
  units: number;
  rate: number;
  amount: number;
}

export interface Bill {
  units: number;
  slabLines: SlabLine[];
  energyCharge: number;
  fixedCharge: number;
  customerCharge: number;
  /** Opt-out surcharge for keeping luxury on during a peak. A PROPOSAL. */
  peakSurcharge: number;
  /** Credit for participating in peak events. Also a proposal. */
  peakReliefCredit: number;
  total: number;
  marginalRate: number;
  slabName: string;
}

/**
 * Telescopic energy charge: each slab bills only the units inside it.
 */
export function energyCharge(units: number): { total: number; lines: SlabLine[] } {
  const lines: SlabLine[] = [];
  let remaining = Math.max(0, units);
  let lower = 0;
  let total = 0;

  for (const slab of TARIFF.slabs) {
    if (remaining <= 0) break;
    const width = slab.upper_kwh === null ? Infinity : slab.upper_kwh - lower;
    const inThisSlab = Math.min(remaining, width);
    const amount = inThisSlab * slab.energy_inr_kwh;
    lines.push({
      label: slab.upper_kwh === null
        ? `above ${lower} kWh`
        : `${lower + 1}–${slab.upper_kwh} kWh`,
      units: Number(inThisSlab.toFixed(2)),
      rate: slab.energy_inr_kwh,
      amount: Number(amount.toFixed(2)),
    });
    total += amount;
    remaining -= inThisSlab;
    lower = slab.upper_kwh ?? lower;
  }
  return { total: Number(total.toFixed(2)), lines };
}

/** The rate the NEXT unit is charged at - what a resident actually feels. */
export function marginalRate(units: number): { rate: number; name: string } {
  let lower = 0;
  for (const slab of TARIFF.slabs) {
    if (slab.upper_kwh === null || units <= slab.upper_kwh) {
      return {
        rate: slab.energy_inr_kwh,
        name: slab.upper_kwh === null
          ? `above ${lower} kWh`
          : `${lower + 1}–${slab.upper_kwh} kWh`,
      };
    }
    lower = slab.upper_kwh;
  }
  const last = TARIFF.slabs[TARIFF.slabs.length - 1];
  return { rate: last.energy_inr_kwh, name: 'top slab' };
}

function customerCharge(units: number): number {
  let lower = 0;
  for (const slab of TARIFF.slabs) {
    if (slab.upper_kwh === null || units <= slab.upper_kwh) {
      return slab.customer_inr_month;
    }
    lower = slab.upper_kwh;
  }
  return TARIFF.slabs[TARIFF.slabs.length - 1].customer_inr_month;
}

export interface BillInput {
  units: number;
  sanctionedLoadKw: number;
  /** Peak events the household opted OUT of, keeping luxury running. */
  optedOutEvents?: number;
  /** Peak events the household participated in. */
  participatedEvents?: number;
}

/** Proposal only - see the module header. Not an APCPDCL charge today. */
export const PROPOSED_OPT_OUT_INR_PER_EVENT = 12.4;
export const PROPOSED_RELIEF_CREDIT_INR_PER_EVENT = 11.67;

export function computeBill({
  units, sanctionedLoadKw, optedOutEvents = 0, participatedEvents = 0,
}: BillInput): Bill {
  const { total: energy, lines } = energyCharge(units);
  const fixed = Number((TARIFF.fixedInrPerKwPerMonth
    * Math.max(1, Math.ceil(sanctionedLoadKw))).toFixed(2));
  const customer = customerCharge(units);
  const surcharge = Number((optedOutEvents * PROPOSED_OPT_OUT_INR_PER_EVENT).toFixed(2));
  const credit = Number((participatedEvents * PROPOSED_RELIEF_CREDIT_INR_PER_EVENT).toFixed(2));
  const { rate, name } = marginalRate(units);

  return {
    units: Number(units.toFixed(2)),
    slabLines: lines,
    energyCharge: energy,
    fixedCharge: fixed,
    customerCharge: customer,
    peakSurcharge: surcharge,
    peakReliefCredit: credit,
    total: Number((energy + fixed + customer + surcharge - credit).toFixed(2)),
    marginalRate: rate,
    slabName: name,
  };
}

export interface ScenarioComparison {
  noControl: Bill;
  ruleBased: Bill;
  sharp: Bill;
  /** SHARP against no control. Negative means SHARP costs less. */
  savingsVsNoControl: number;
}

/**
 * The three-scenario comparison the idea book asks for (§44).
 *
 * Be ready for the honest result: with no time-of-day rate, SHARP moves load
 * without moving the bill much, and the rule-based controller can win on cost
 * while losing on peak. Show it rather than hide it - the winnable metrics here
 * are peak and PAR, not rupees.
 */
export function compareScenarios(
  unitsNoControl: number,
  sanctionedLoadKw: number,
  opts: { ruleBasedUnits?: number; sharpUnits?: number } = {},
): ScenarioComparison {
  const noControl = computeBill({ units: unitsNoControl, sanctionedLoadKw });
  const ruleBased = computeBill({
    units: opts.ruleBasedUnits ?? unitsNoControl * 0.958,
    sanctionedLoadKw,
  });
  // NO proposed credits in the comparison. Applying a participation credit
  // only to the SHARP arm would make it "cheapest" on the strength of a tariff
  // mechanism that does not exist today - a rigged comparison, and the first
  // thing a reviewer would pull apart. The three arms are compared on energy
  // alone; the proposed surcharge and credit appear as their own labelled
  // lines in the breakdown, where they can be read as proposals.
  const sharp = computeBill({
    units: opts.sharpUnits ?? unitsNoControl * 0.988,
    sanctionedLoadKw,
  });
  return {
    noControl, ruleBased, sharp,
    savingsVsNoControl: Number((noControl.total - sharp.total).toFixed(2)),
  };
}

export const BILL_DISCLAIMER =
  'Estimated from simulated interval energy on the APCPDCL FY2025-26 order '
  + 'components. Electricity duty, FPPCA, true-up and subsidies are excluded, '
  + 'so this is not a full utility bill. Peak surcharges and relief credits are '
  + 'a PROPOSAL under the 2023 Rules — APCPDCL has no domestic time-of-day rate '
  + 'today.';
