'use client';

import React, { useState } from 'react';
import { HomeState, PeakEvent } from '@/lib/contracts';
import { TechQuickNav, TechTab } from './TechQuickNav';

const LEAD_TIME = { min: 5, max: 15, step: 5, default: 15 };

interface Props {
  homeState: HomeState;
  peakEvent: PeakEvent;
  activeScenario?: 'normal' | 'peak' | 'outage';
  onScenarioChange?: (scenario: 'normal' | 'peak' | 'outage') => void;
  initialTab?: TechTab;
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

export function TechnicalView({ homeState, peakEvent, initialTab = 'policy' }: Props) {
  const [activeTab, setActiveTab] = useState<TechTab>(initialTab);
  const [leadTime, setLeadTime] = useState(LEAD_TIME.default);

  return (
    <div className="space-y-6">
      {/* Technical Top Quick Links Navigation Bar */}
      <TechQuickNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        leadTimeMinutes={leadTime}
      />

      {/* ---------------- TAB 1: POLICY MODEL ---------------- */}
      {activeTab === 'policy' && (
        <section className="card p-6 space-y-4">
          <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
            <div>
              <p className="eyebrow">Policy Checkpoint</p>
              <h3 className="text-lg font-bold" style={{ color: 'var(--navy)' }}>
                Branching Dueling Double-Q (BDQ) Architecture
              </h3>
            </div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              SAFETY SHIELD ACTIVE
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Row label="Parameters" value="50,133" hint="196 KB, float32 checkpoint" />
              <Row label="State Vector" value="305 features" hint="28 action branches × 3 levels" />
              <Row label="Balanced Accuracy" value="0.6232" hint="random baseline is 0.3333" />
            </div>

            <div>
              <Row label="Peak Demand Reduction" value="8.5 %" hint="60 simulated days × 3 seeds" />
              <Row label="Critical Loads Shed" value="0" hint="while occupant wanted them" />
              <Row label="Illegal Actions" value="0" hint="strict safety layer constraint" />
            </div>
          </div>

          <p className="mt-3 text-[11.5px] leading-relaxed rounded-xl p-3.5"
             style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--slate)' }}>
            Level 2 (dim) exists in the action space and is never selected: no critical load may be dimmed, which leaves 44 air coolers of 4,124 devices able to dim at all.
          </p>
        </section>
      )}

      {/* ---------------- TAB 2: LEAD TIME & NOTICE ---------------- */}
      {activeTab === 'notice' && (
        <section className="card p-6 space-y-4">
          <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
            <div>
              <p className="eyebrow">Peak Notice Configuration</p>
              <h3 className="text-lg font-bold" style={{ color: 'var(--navy)' }}>
                Lead Time Before Load Shedding
              </h3>
            </div>
            <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-blue-100 text-blue-800">
              {leadTime} MIN NOTICE
            </span>
          </div>

          <p className="text-[13px]" style={{ color: 'var(--slate)' }}>
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
            className="mt-3 w-full cursor-pointer h-2 bg-slate-200 rounded-lg accent-blue-600"
            aria-label="Lead time in minutes"
          />
          <div className="flex justify-between text-[11px] font-mono" style={{ color: 'var(--slate-soft)' }}>
            <span>{LEAD_TIME.min} min (Minimum)</span>
            <span>{LEAD_TIME.max} min (Maximum)</span>
          </div>

          <p className="mt-3 rounded-[11px] p-3 text-[11px] leading-relaxed"
             style={{ background: 'var(--yellow-tint)', color: 'var(--yellow-ink)' }}>
            Bounded on purpose. Below {LEAD_TIME.min} minutes nobody can realistically react, and human override is the whole point of SHARP. Above {LEAD_TIME.max} the plan shown may be superseded before it lands — that is one control interval.
          </p>
        </section>
      )}

      {/* ---------------- TAB 3: LIVE TELEMETRY ---------------- */}
      {activeTab === 'telemetry' && (
        <section className="card p-6 space-y-4">
          <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
            <div>
              <p className="eyebrow">Live State</p>
              <h3 className="text-lg font-bold" style={{ color: 'var(--navy)' }}>
                What the Raspberry Pi Believes
              </h3>
            </div>
            <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-100 text-emerald-800">
              HOUSE: {homeState.house_id}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Row label="House ID" value={homeState.house_id} />
              <Row label="Operating Mode" value={homeState.operating_mode.replace(/_/g, ' ')} />
              <Row label="Grid Severity" value={homeState.grid_peak_severity.toFixed(2)}
                   hint={peakEvent.is_active ? 'event active' : 'historical curve'} />
            </div>

            <div>
              <Row label="Indoor Temperature" value={`${homeState.indoor_temperature_c.toFixed(1)} °C`}
                   hint="estimated thermal model" />
              <Row label="Outdoor Temperature" value={`${homeState.outdoor_temperature_c.toFixed(1)} °C`} />
              <Row label="Appliances Registered" value={String(homeState.appliances?.length ?? 0)} />
            </div>
          </div>

          <p className="mt-3 rounded-[11px] p-3 text-[11px] leading-relaxed"
             style={{ background: 'var(--primary-tint)', color: 'var(--primary-ink)' }}>
            Appliance power is derived from verified switch state multiplied by a catalogued wattage. <code>measured_w</code> is null because no meter is fitted — faking it would make a stuck relay invisible.
          </p>
        </section>
      )}
    </div>
  );
}
