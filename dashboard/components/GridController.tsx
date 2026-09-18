'use client';

import React, { useState } from 'react';
import {
  Radio,
  Sliders,
  Send,
  XCircle,
  CheckCircle2,
  Zap,
  Users,
} from 'lucide-react';

import { PeakEvent, HomeState } from '@/lib/contracts';
import { GridQuickNav, GridTab } from './GridQuickNav';

interface GridControllerProps {
  peakEvent: PeakEvent;
  homeState?: HomeState;
  onDeclarePeak: (
    severity: number,
    durationMinutes: number
  ) => void;
  onCancelPeak: () => void;
  initialTab?: GridTab;
}

export function GridController({
  peakEvent,
  onDeclarePeak,
  onCancelPeak,
  initialTab = 'dispatch',
}: GridControllerProps) {
  const [activeTab, setActiveTab] = useState<GridTab>(initialTab);
  const [severity, setSeverity] = useState<number>(0.67);
  const [duration, setDuration] = useState<number>(60);
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);

  const handleDeclare = () => {
    onDeclarePeak(severity, duration);
    setLastActionMessage(
      `Broadcast sent: Severity ${severity.toFixed(2)} dispatched to Guntur Urban Sub-12.`
    );
  };

  const handleCancel = () => {
    onCancelPeak();
    setLastActionMessage(
      'Peak event cancelled. Feeders returned to normal baseline.'
    );
  };

  const handleToggleEvent = () => {
    if (peakEvent.is_active) {
      handleCancel();
    } else {
      handleDeclare();
    }
  };

  const setPreset = (sev: number, dur: number) => {
    setSeverity(sev);
    setDuration(dur);
  };

  const severityBadgeClass =
    severity >= 0.65
      ? 'border-rose-400 bg-rose-50 text-rose-700'
      : severity >= 0.4
      ? 'border-amber-400 bg-amber-50 text-amber-700'
      : 'border-emerald-400 bg-emerald-50 text-emerald-700';

  return (
    <div className="space-y-6">
      {/* Grid Top Quick Links Navigation Bar */}
      <GridQuickNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isPeakActive={peakEvent.is_active}
        severity={severity}
      />

      {/* HEADER WITH RED/GREEN TOGGLE SWITCH */}
      <div className="relative overflow-hidden rounded-2xl border border-[#e5eaf2] bg-[#eaf4ff] p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${peakEvent.is_active ? 'bg-rose-500 animate-ping' : 'bg-emerald-500'}`} />
              <span className="font-mono text-xs font-bold tracking-widest text-[#0f2d4a] uppercase">
                DISCOM Operator Console
              </span>
            </div>
            <h2 className="text-xl font-bold text-[#17365D]">
              Distribution Feeder Stress &amp; Peak Management
            </h2>
            <p className="text-xs text-[#6b7c93]/80">
              Authority: APCPDCL Regional Grid Operations • Feeder: Guntur Urban Sub-12 (431 Enrolled Smart Homes)
            </p>
          </div>

          <div className="flex items-center gap-4 bg-white px-4 py-2.5 rounded-xl border border-[#e5eaf2] shadow-sm">
            <div className="text-right">
              <span className="block text-[10px] text-[#9aa8bd] font-semibold uppercase">
                Feeder Status
              </span>
              <span className={`font-mono text-xs font-bold ${peakEvent.is_active ? 'text-rose-600' : 'text-emerald-600'}`}>
                {peakEvent.is_active ? 'PEAK MITIGATION ACTIVE' : 'NOMINAL BASELINE'}
              </span>
            </div>

            {/* RED / GREEN PEAK EVENT DISPATCH TOGGLE SWITCH */}
            <button
              type="button"
              onClick={handleToggleEvent}
              title={peakEvent.is_active ? "Cancel Peak Mitigation" : "Dispatch Peak Mitigation"}
              className={`relative inline-flex h-8 w-16 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                peakEvent.is_active ? 'bg-rose-500 focus:ring-rose-500' : 'bg-emerald-500 focus:ring-emerald-500'
              }`}
              role="switch"
              aria-checked={peakEvent.is_active}
            >
              <span className="sr-only">Toggle Grid Peak Event</span>
              <span
                className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out flex items-center justify-center text-[9px] font-extrabold ${
                  peakEvent.is_active ? 'translate-x-8 text-rose-600' : 'translate-x-0 text-emerald-600'
                }`}
              >
                {peakEvent.is_active ? 'PEAK' : 'NORM'}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* ACTION FEEDBACK */}
      {lastActionMessage && (
        <div className="flex items-center justify-between rounded-xl border border-[#e5eaf2] bg-[#eaf4ff] px-4 py-2.5 text-xs text-[#0f2d4a]">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-[#6b7c93]" />
            <span>{lastActionMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setLastActionMessage(null)}
            className="text-[#6b7c93] hover:text-[#0f2d4a] cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ---------------- TAB 1: DISPATCH ---------------- */}
      {activeTab === 'dispatch' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* LEFT — DECLARATION */}
          <div className="space-y-6 lg:col-span-7">
            <div className="rounded-2xl border border-[#e5eaf2] bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-[#e5eaf2] pb-4">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#e5eaf2] bg-[#eaf4ff] text-[#6b7c93]">
                    <Sliders className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="font-mono text-sm font-bold text-[#17365D]">
                      DECLARE DEMAND-RESPONSE PEAK EVENT
                    </h3>
                    <p className="text-xs text-[#6b7c93]">
                      Dispatches authenticated peak signal to participating household SHARP controllers
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-5 space-y-5">
                {/* Presets */}
                <div>
                  <label className="mb-2 block text-xs font-semibold tracking-wide text-[#6b7c93]">
                    Standard Demo Scenarios
                  </label>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                    <button
                      type="button"
                      onClick={() => setPreset(0.67, 60)}
                      className={`rounded-lg border p-2.5 text-left transition-all cursor-pointer ${
                        severity === 0.67
                          ? 'border-blue-400 bg-[#eaf4ff] text-[#0f2d4a]'
                          : 'border-[#e5eaf2] bg-white text-[#6b7c93] hover:border-[#e5eaf2] hover:bg-[#eaf4ff]'
                      }`}
                    >
                      <div className="font-mono text-xs font-bold text-[#17365D]">
                        Midday Feeder Peak
                      </div>
                      <div className="mt-0.5 text-[11px] text-[#6b7c93]">
                        14:05 IST • Sev: 0.67
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setPreset(0.48, 45)}
                      className={`rounded-lg border p-2.5 text-left transition-all cursor-pointer ${
                        severity === 0.48
                          ? 'border-[#d7e3f2] bg-[#eaf4ff] text-[#0f2d4a]'
                          : 'border-[#e5eaf2] bg-white text-[#6b7c93] hover:border-[#e5eaf2] hover:bg-[#eaf4ff]'
                      }`}
                    >
                      <div className="font-mono text-xs font-bold text-[#17365D]">
                        Solar Ramping Drop
                      </div>
                      <div className="mt-0.5 text-[11px] text-[#6b7c93]">
                        16:15 IST • Sev: 0.48
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setPreset(0.15, 30)}
                      className={`rounded-lg border p-2.5 text-left transition-all cursor-pointer ${
                        severity === 0.15
                          ? 'border-[#e5eaf2] bg-[#eaf4ff] text-[#0f2d4a]'
                          : 'border-[#e5eaf2] bg-white text-[#6b7c93] hover:border-[#e5eaf2] hover:bg-[#eaf4ff]'
                      }`}
                    >
                      <div className="font-mono text-xs font-bold text-[#17365D]">
                        Normal Baseline
                      </div>
                      <div className="mt-0.5 text-[11px] text-[#6b7c93]">
                        11:00 IST • Sev: 0.15
                      </div>
                    </button>
                  </div>
                </div>

                {/* Severity */}
                <div className="space-y-3 rounded-xl border border-[#e5eaf2] bg-[#eaf4ff]/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-[#0f2d4a]">
                      Grid Stress Severity
                    </span>
                    <span className={`rounded border px-2 py-0.5 font-mono text-xs font-bold ${severityBadgeClass}`}>
                      {severity.toFixed(2)} / 1.00
                    </span>
                  </div>

                  <input
                    type="range"
                    min={0.0}
                    max={1.0}
                    step={0.01}
                    value={severity}
                    onChange={(e) => setSeverity(parseFloat(e.target.value))}
                    className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-blue-200 accent-blue-600"
                  />

                  <div className="flex justify-between font-mono text-[10px] text-[#9aa8bd]">
                    <span>0.00 Relaxed</span>
                    <span>0.40 Advisory</span>
                    <span>0.67 Midday Peak</span>
                    <span>1.00 Critical</span>
                  </div>
                </div>

                {/* Duration */}
                <div>
                  <label className="mb-2 block text-xs font-semibold tracking-wide text-[#6b7c93]">
                    Event Duration
                  </label>
                  <div className="grid grid-cols-4 gap-2">
                    {[30, 60, 90, 120].map((mins) => (
                      <button
                        key={mins}
                        type="button"
                        onClick={() => setDuration(mins)}
                        className={`rounded-lg border py-2 text-center font-mono text-xs font-semibold transition-all cursor-pointer ${
                          duration === mins
                            ? 'border-[#d7e3f2] bg-[#eaf4ff] text-[#0f2d4a]'
                            : 'border-[#e5eaf2] bg-white text-[#6b7c93] hover:border-[#e5eaf2] hover:bg-[#eaf4ff]'
                        }`}
                      >
                        {mins} min
                      </button>
                    ))}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={handleDeclare}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 font-mono text-xs font-bold text-white shadow-sm transition-all hover:bg-blue-700 active:scale-95 cursor-pointer"
                  >
                    <Send className="h-4 w-4" />
                    DECLARE PEAK EVENT (BROADCAST)
                  </button>

                  {peakEvent.is_active && (
                    <button
                      type="button"
                      onClick={handleCancel}
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 font-mono text-xs font-semibold text-rose-700 transition-all hover:bg-rose-100 cursor-pointer"
                    >
                      <XCircle className="h-4 w-4 text-rose-600" />
                      CANCEL EVENT
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT — STATUS */}
          <div className="space-y-6 lg:col-span-5">
            <div
              className={`rounded-2xl border p-5 shadow-sm transition-all ${
                peakEvent.is_active
                  ? 'border-rose-200 bg-rose-50/40'
                  : 'border-[#e5eaf2] bg-white'
              }`}
            >
              <div className="flex items-center justify-between border-b border-[#e5eaf2] pb-3">
                <div className="flex items-center gap-2">
                  <Radio
                    className={`h-4 w-4 ${
                      peakEvent.is_active ? 'text-rose-600 animate-pulse' : 'text-[#9aa8bd]'
                    }`}
                  />
                  <h4 className="font-mono text-xs font-bold tracking-wider uppercase text-[#17365D]">
                    {peakEvent.is_active ? 'PEAK EVENT BROADCAST ACTIVE' : 'NO ACTIVE BROADCAST'}
                  </h4>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                    peakEvent.is_active ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-white'
                  }`}
                >
                  {peakEvent.is_active ? 'ACTIVE' : 'IDLE'}
                </span>
              </div>

              <div className="mt-4 space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between text-[#6b7c93]">
                  <span>Event Identifier:</span>
                  <span className="font-semibold text-[#17365D]">{peakEvent.event_id}</span>
                </div>
                <div className="flex items-center justify-between text-[#6b7c93]">
                  <span>Current Severity:</span>
                  <span className="font-bold text-[#0f2d4a]">{peakEvent.severity.toFixed(2)}</span>
                </div>
                <div className="flex items-center justify-between text-[#6b7c93]">
                  <span>Declared Time:</span>
                  <span className="text-[#0f2d4a]">{peakEvent.declared_at}</span>
                </div>
                <div className="flex items-center justify-between text-[#6b7c93]">
                  <span>Auto-Expiry:</span>
                  <span className="text-[#0f2d4a]">{peakEvent.expires_at}</span>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3 border-t border-[#e5eaf2] pt-4">
                <div className="rounded-lg border border-[#e5eaf2] bg-white p-2.5">
                  <div className="flex items-center gap-1.5 text-[#6b7c93] text-[10px]">
                    <Users className="h-3 w-3 text-[#6b7c93]" />
                    <span>Homes Shedding</span>
                  </div>
                  <p className="mt-1 font-mono text-base font-bold text-[#17365D]">
                    {peakEvent.is_active ? peakEvent.homes_responding ?? 431 : 0} / 431
                  </p>
                </div>

                <div className="rounded-lg border border-[#e5eaf2] bg-white p-2.5">
                  <div className="flex items-center gap-1.5 text-[#6b7c93] text-[10px]">
                    <Zap className="h-3 w-3 text-[#6b7c93]" />
                    <span>Feeder Relief</span>
                  </div>
                  <p className="mt-1 font-mono text-base font-bold text-[#0f2d4a]">
                    {peakEvent.is_active ? `${peakEvent.mw_relieved ?? 0.28} MW` : '0.00 MW'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------- TAB 2: FEEDER TELEMETRY ---------------- */}
      {activeTab === 'feeder' && (
        <div className="rounded-2xl border border-[#e5eaf2] bg-white p-6 shadow-sm space-y-6">
          <div className="flex items-center justify-between border-b border-[#e5eaf2] pb-4">
            <div>
              <h3 className="font-mono text-base font-bold text-[#17365D]">
                GUNTUR URBAN SUB-12 FEEDER TELEMETRY
              </h3>
              <p className="text-xs text-[#6b7c93]">
                431 Enrolled Smart Homes • Transformer Capacity: 1.5 MVA • Grid Frequency: 50.02 Hz
              </p>
            </div>
            <span className="rounded-full bg-emerald-100 px-3 py-1 font-mono text-xs font-bold text-emerald-800">
              SUBSTATION ONLINE
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-xl border border-[#e5eaf2] bg-[#f8fafc] p-4">
              <span className="text-xs text-slate-500 font-semibold uppercase">Total Feeder Load</span>
              <p className="mt-1 text-2xl font-mono font-bold text-slate-900">
                {peakEvent.is_active ? '0.94 MW' : '1.22 MW'}
              </p>
              <span className="text-[11px] text-slate-500">Sanctioned limit: 1.50 MW</span>
            </div>

            <div className="rounded-xl border border-[#e5eaf2] bg-[#f8fafc] p-4">
              <span className="text-xs text-slate-500 font-semibold uppercase">DR Participation Rate</span>
              <p className="mt-1 text-2xl font-mono font-bold text-emerald-600">
                {peakEvent.is_active ? '100 %' : '0 %'}
              </p>
              <span className="text-[11px] text-slate-500">431 / 431 Active Shield Nodes</span>
            </div>

            <div className="rounded-xl border border-[#e5eaf2] bg-[#f8fafc] p-4">
              <span className="text-xs text-slate-500 font-semibold uppercase">Peak Relief Capacity</span>
              <p className="mt-1 text-2xl font-mono font-bold text-blue-600">
                0.28 MW
              </p>
              <span className="text-[11px] text-slate-500">Guaranteed non-necessity load relief</span>
            </div>
          </div>
        </div>
      )}

      {/* ---------------- TAB 3: SIGNAL HISTORY ---------------- */}
      {activeTab === 'history' && (
        <div className="rounded-2xl border border-[#e5eaf2] bg-white p-6 shadow-sm space-y-4">
          <h3 className="font-mono text-base font-bold text-[#17365D] border-b border-[#e5eaf2] pb-3">
            BROADCAST LOG &amp; AUDIT TRAIL
          </h3>
          
          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between rounded-lg border border-[#e5eaf2] bg-slate-50 p-3">
              <div className="flex items-center gap-3">
                <span className={`h-2.5 w-2.5 rounded-full ${peakEvent.is_active ? 'bg-rose-500' : 'bg-slate-400'}`} />
                <div>
                  <span className="font-bold text-slate-900">{peakEvent.event_id}</span>
                  <span className="block text-[11px] text-slate-500">Scope: {peakEvent.region}</span>
                </div>
              </div>
              <div className="text-right">
                <span className="font-bold text-slate-900">Sev {peakEvent.severity.toFixed(2)}</span>
                <span className="block text-[11px] text-slate-500">{peakEvent.declared_at}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}