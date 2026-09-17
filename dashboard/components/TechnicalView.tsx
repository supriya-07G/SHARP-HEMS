'use client';

/**
 * The technical role: what the model is, what it is allowed to do, and the one
 * setting the team can change during a demo.
 *
 * Deliberately plain. This view exists to answer a reviewer's questions
 * directly - which checkpoint, measured how, on what data - rather than to
 * look impressive.
 */

import { useState } from 'react';
import { HomeState, PeakEvent } from '@/lib/contracts';

/** Bounds are enforced, not advised. A notice of zero would remove the
 *  resident's chance to object, and human override is the project's core
 *  claim - it must be impossible to configure that away. Above one control
 *  interval the plan shown may be superseded before it lands. */
const LEAD_TIME = { min: 5, max: 15, step: 5, default: 15 };

interface Props {
  homeState: HomeState;
  peakEvent: PeakEvent;
  activeScenario: 'normal' | 'peak' | 'outage';
  onScenarioChange: (scenario: 'normal' | 'peak' | 'outage') => void;
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5"
         style={{ borderBottom: '1px solid var(--border)' }}>
      <span className="text-[12.5px]" style={{ color: 'var(--slate)' }}>{label}</span>
      <span className="text-right">
        <span className="text-[13px] font-semibold" style={{ color: 'var(--navy)' }}>
          {value}
        </span>
        {hint && (
          <span className="block text-[10.5px]" style={{ color: 'var(--slate-soft)' }}>
            {hint}
          </span>
        )}
      </span>
    </div>
  );
}

export function TechnicalView({ homeState, peakEvent }: Props) {
  const [leadTime, setLeadTime] = useState(LEAD_TIME.default);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Peak notice ------------------------------------------------------ */}
      <section className="card p-5 lg:col-span-1">
        <p className="eyebrow">Peak notice</p>
        <h3 className="mt-1 text-[15px] font-semibold" style={{ color: 'var(--navy)' }}>
          Lead time before shedding
        </h3>
        <p className="mt-1.5 text-[12px] leading-relaxed" style={{ color: 'var(--slate)' }}>
          How long the resident gets to object before luxury loads pause.
        </p>

        <div className="mt-4 flex items-baseline gap-2">
          <span className="metric">{leadTime}</span>
          <span className="text-[13px]" style={{ color: 'var(--slate)' }}>minutes</span>
        </div>

        <input
          type="range"
          min={LEAD_TIME.min}
          max={LEAD_TIME.max}
          step={LEAD_TIME.step}
          value={leadTime}
          onChange={(e) => setLeadTime(Number(e.target.value))}
          className="mt-3 w-full"
          style={{ accentColor: 'var(--primary)' }}
          aria-label="Lead time in minutes"
        />
        <div className="flex justify-between text-[10.5px]" style={{ color: 'var(--slate-soft)' }}>
          <span>{LEAD_TIME.min} min</span>
          <span>{LEAD_TIME.max} min</span>
        </div>

        <p className="mt-3 rounded-[11px] p-3 text-[11px] leading-relaxed"
           style={{ background: 'var(--yellow-tint)', color: 'var(--yellow-ink)' }}>
          Bounded on purpose. Below {LEAD_TIME.min} minutes nobody can
          realistically react, and human override is the whole point of SHARP.
          Above {LEAD_TIME.max} the plan shown may be superseded before it lands
          — that is one control interval.
        </p>
      </section>

      {/* The model -------------------------------------------------------- */}
      <section className="card p-5 lg:col-span-1">
        <p className="eyebrow">Policy</p>
        <h3 className="mt-1 text-[15px] font-semibold" style={{ color: 'var(--navy)' }}>
          Branching Dueling Double-Q
        </h3>
        <div className="mt-3">
          <Row label="Parameters" value="50,133" hint="196 KB, float32" />
          <Row label="State" value="305 features" hint="28 branches × 3 levels" />
          <Row label="Balanced accuracy" value="0.6232" hint="chance is 0.3333" />
          <Row label="Peak reduction" value="8.5 %" hint="60 days × 3 seeds" />
          <Row label="Critical loads shed" value="0" hint="while the occupant wanted them" />
          <Row label="Illegal actions" value="0" />
        </div>
        <p className="mt-3 text-[11px] leading-relaxed" style={{ color: 'var(--slate-soft)' }}>
          Level 2 (dim) exists in the action space and is never selected: no
          critical load may be dimmed, which leaves 44 air coolers of 4,124
          devices able to dim at all.
        </p>
      </section>

      {/* Live state ------------------------------------------------------- */}
      <section className="card p-5 lg:col-span-1">
        <p className="eyebrow">Live state</p>
        <h3 className="mt-1 text-[15px] font-semibold" style={{ color: 'var(--navy)' }}>
          What the Pi believes
        </h3>
        <div className="mt-3">
          <Row label="House" value={homeState.house_id} />
          <Row label="Operating mode" value={homeState.operating_mode.replace(/_/g, ' ')} />
          <Row label="Grid severity" value={homeState.grid_peak_severity.toFixed(2)}
               hint={peakEvent.is_active ? 'event active' : 'historical curve'} />
          <Row label="Indoor" value={`${homeState.indoor_temperature_c.toFixed(1)} °C`}
               hint="estimated, no sensor fitted" />
          <Row label="Outdoor" value={`${homeState.outdoor_temperature_c.toFixed(1)} °C`} />
          <Row label="Appliances" value={String(homeState.appliances?.length ?? 0)} />
        </div>
        <p className="mt-3 rounded-[11px] p-3 text-[11px] leading-relaxed"
           style={{ background: 'var(--primary-tint)', color: 'var(--primary-ink)' }}>
          Appliance power is derived from verified switch state multiplied by a
          catalogued wattage. <code>measured_w</code> is null because no meter is
          fitted — faking it would make a stuck relay invisible.
        </p>
      </section>
    </div>
  );
}
