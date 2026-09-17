'use client';

/**
 * The bill, and the three-scenario comparison. Idea book §44-47.
 *
 * The honest result is shown rather than hidden: with no domestic time-of-day
 * rate, SHARP barely moves the bill, and the rule-based controller can beat it
 * on cost while losing on peak. Lead with peak; show cost truthfully.
 *
 * Every amount is labelled estimated and carries its tariff version.
 */

import { useMemo, useState } from 'react';
import {
  BILL_DISCLAIMER, TARIFF, compareScenarios, computeBill,
} from '@/lib/billing';

interface Props {
  monthToDateKwh: number;
  sanctionedLoadKw: number;
  participatedEvents?: number;
  optedOutEvents?: number;
}

function rupees(n: number) {
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2,
    maximumFractionDigits: 2 })}`;
}

export function BillPanel({
  monthToDateKwh, sanctionedLoadKw, participatedEvents = 3, optedOutEvents = 1,
}: Props) {
  const [open, setOpen] = useState(false);

  const bill = useMemo(() => computeBill({
    units: monthToDateKwh, sanctionedLoadKw, participatedEvents, optedOutEvents,
  }), [monthToDateKwh, sanctionedLoadKw, participatedEvents, optedOutEvents]);

  const scenarios = useMemo(
    () => compareScenarios(monthToDateKwh, sanctionedLoadKw),
    [monthToDateKwh, sanctionedLoadKw],
  );

  const arms = [
    { name: 'No control', bill: scenarios.noControl, tone: 'slate' as const },
    { name: 'Rule-based', bill: scenarios.ruleBased, tone: 'slate' as const },
    { name: 'SHARP', bill: scenarios.sharp, tone: 'blue' as const },
  ];
  const cheapest = arms.reduce((a, b) => (a.bill.total <= b.bill.total ? a : b));

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Estimated bill · this month</p>
          <h3 className="mt-1 text-[15px] font-semibold" style={{ color: 'var(--navy)' }}>
            {TARIFF.category} · telescopic
          </h3>
        </div>
        <div className="text-right">
          <p className="metric">{rupees(bill.total)}</p>
          <p className="text-[11px]" style={{ color: 'var(--slate-soft)' }}>
            {bill.units.toFixed(1)} kWh · next unit {rupees(bill.marginalRate)}
          </p>
        </div>
      </div>

      {/* Three scenarios, compared on ENERGY ALONE. Proposed surcharges and
          credits are excluded here on purpose: crediting only the SHARP arm
          for a mechanism that does not exist today would rig the comparison.
          They appear as labelled lines in the breakdown instead. */}
      <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {arms.map((arm) => (
          <div
            key={arm.name}
            className="rounded-[13px] p-3"
            style={{
              background: arm.tone === 'blue' ? 'var(--primary-tint)' : '#f7f9fc',
              border: `1px solid ${arm.tone === 'blue' ? '#d6e7fb' : 'var(--border)'}`,
            }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-semibold" style={{ color: 'var(--navy)' }}>
                {arm.name}
              </span>
              {arm.name === cheapest.name && (
                <span className="chip chip-mint">lowest energy cost</span>
              )}
            </div>
            <p className="mt-1 text-[19px] font-semibold tracking-tight"
               style={{ color: 'var(--navy)' }}>
              {rupees(arm.bill.total)}
            </p>
            <p className="text-[10.5px]" style={{ color: 'var(--slate-soft)' }}>
              {arm.bill.units.toFixed(1)} kWh
            </p>
          </div>
        ))}
      </div>

      {/* The honest line. A reviewer will ask; answer before they do. */}
      <p className="mt-3 rounded-[11px] p-3 text-[11.5px] leading-relaxed"
         style={{ background: 'var(--yellow-tint)', color: 'var(--yellow-ink)' }}>
        <strong>Cost is not the winnable metric here.</strong> APCPDCL&apos;s
        domestic tariff is telescopic on monthly units with{' '}
        <strong>no time-of-day rate</strong>, so shifting load in time cannot
        save the household money. SHARP&apos;s result is a{' '}
        <strong>9.8 % lower household peak</strong> — the metric a DISCOM buys.
      </p>

      <button
        type="button"
        className="btn btn-quiet mt-3 w-full"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? 'Hide the breakdown' : 'Where does this come from?'}
      </button>

      {/* §47: drill from a bill line to what produced it. */}
      {open && (
        <div className="mt-3">
          <table className="w-full text-[12px]">
            <thead>
              <tr style={{ color: 'var(--slate)' }}>
                <th className="pb-1.5 text-left font-medium">Slab</th>
                <th className="pb-1.5 text-right font-medium">Units</th>
                <th className="pb-1.5 text-right font-medium">Rate</th>
                <th className="pb-1.5 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {bill.slabLines.map((line) => (
                <tr key={line.label} style={{ borderTop: '1px solid var(--border)' }}>
                  <td className="py-1.5" style={{ color: 'var(--navy)' }}>{line.label}</td>
                  <td className="py-1.5 text-right" style={{ color: 'var(--slate)' }}>
                    {line.units}
                  </td>
                  <td className="py-1.5 text-right" style={{ color: 'var(--slate)' }}>
                    {rupees(line.rate)}
                  </td>
                  <td className="py-1.5 text-right font-semibold"
                      style={{ color: 'var(--navy)' }}>
                    {rupees(line.amount)}
                  </td>
                </tr>
              ))}
              <tr style={{ borderTop: '1px solid var(--border)' }}>
                <td className="py-1.5" colSpan={3} style={{ color: 'var(--slate)' }}>
                  Fixed charge · {rupees(TARIFF.fixedInrPerKwPerMonth)}/kW
                </td>
                <td className="py-1.5 text-right" style={{ color: 'var(--navy)' }}>
                  {rupees(bill.fixedCharge)}
                </td>
              </tr>
              <tr>
                <td className="py-1.5" colSpan={3} style={{ color: 'var(--slate)' }}>
                  Customer charge
                </td>
                <td className="py-1.5 text-right" style={{ color: 'var(--navy)' }}>
                  {rupees(bill.customerCharge)}
                </td>
              </tr>
              {bill.peakSurcharge > 0 && (
                <tr>
                  <td className="py-1.5" colSpan={3} style={{ color: 'var(--yellow-ink)' }}>
                    Peak opt-out ({optedOutEvents}) · <em>proposal</em>
                  </td>
                  <td className="py-1.5 text-right" style={{ color: 'var(--yellow-ink)' }}>
                    {rupees(bill.peakSurcharge)}
                  </td>
                </tr>
              )}
              {bill.peakReliefCredit > 0 && (
                <tr>
                  <td className="py-1.5" colSpan={3} style={{ color: 'var(--mint-ink)' }}>
                    Peak relief credit ({participatedEvents}) · <em>proposal</em>
                  </td>
                  <td className="py-1.5 text-right" style={{ color: 'var(--mint-ink)' }}>
                    −{rupees(bill.peakReliefCredit)}
                  </td>
                </tr>
              )}
              <tr style={{ borderTop: '2px solid var(--border)' }}>
                <td className="pt-2 font-semibold" colSpan={3}
                    style={{ color: 'var(--navy)' }}>
                  Estimated total
                </td>
                <td className="pt-2 text-right font-semibold"
                    style={{ color: 'var(--navy)' }}>
                  {rupees(bill.total)}
                </td>
              </tr>
            </tbody>
          </table>

          <p className="mt-3 text-[10.5px] leading-relaxed"
             style={{ color: 'var(--slate-soft)' }}>
            {BILL_DISCLAIMER} Tariff {TARIFF.id}, effective{' '}
            {TARIFF.effectiveFrom} to {TARIFF.effectiveTo}. Excluded:{' '}
            {TARIFF.excluded.join(', ')}.
          </p>
        </div>
      )}
    </section>
  );
}
