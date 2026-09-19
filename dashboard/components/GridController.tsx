'use client';

import React, { useState } from 'react';
import { Radio, Send, XCircle, Zap, Cpu } from 'lucide-react';
import { PeakEvent, HomeState } from '@/lib/contracts';
import { GridQuickNav, GridTab } from './GridQuickNav';

interface GridControllerProps {
  peakEvent: PeakEvent;
  homeState: HomeState;
  onDeclarePeak: (severity: number, durationMinutes: number) => void;
  onCancelPeak: () => void;
  initialTab?: GridTab;
}

export function GridController({
  peakEvent,
  homeState,
  onDeclarePeak,
  onCancelPeak,
  initialTab = 'dispatch',
}: GridControllerProps) {
  const [activeTab, setActiveTab] = useState<GridTab>(initialTab);
  const [severity, setSeverity] = useState<number>(
    Math.max(0, Math.min(1, homeState.grid_peak_severity)),
  );
  const [duration, setDuration] = useState<number>(60);
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);

  const handleDeclare = () => {
    onDeclarePeak(severity, duration);
    setLastActionMessage(
      `Grid event published to HiveMQ: severity ${severity.toFixed(2)}, duration ${duration} min. Waiting for edge/runtime confirmation.`,
    );
  };

  const handleCancel = () => {
    onCancelPeak();
    setLastActionMessage(
      'Grid-event cancellation published to HiveMQ. Waiting for edge/runtime confirmation.',
    );
  };

  return (
    <div className="space-y-6">
      <GridQuickNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isPeakActive={peakEvent.is_active}
        severity={homeState.grid_peak_severity}
      />

      {activeTab === 'dispatch' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <section className="card p-6 lg:col-span-7">
            <div className="flex items-center gap-2 border-b pb-3" style={{ borderColor: 'var(--border)' }}>
              <Radio className="h-4 w-4 text-blue-600" />
              <div>
                <p className="eyebrow">Grid event control</p>
                <h3 className="font-semibold" style={{ color: 'var(--navy)' }}>
                  Publish demand-response severity
                </h3>
              </div>
            </div>

            <p className="mt-4 text-xs leading-relaxed" style={{ color: 'var(--slate)' }}>
              This control publishes an authenticated event to HiveMQ. It does not mutate
              dashboard state locally. The visible severity changes only when the edge/runtime
              path receives and republishes the event.
            </p>

            <div className="mt-5 space-y-4">
              <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border)' }}>
                <div className="flex items-center justify-between text-xs">
                  <span style={{ color: 'var(--slate)' }}>Requested severity</span>
                  <strong className="font-mono" style={{ color: 'var(--navy)' }}>
                    {severity.toFixed(2)}
                  </strong>
                </div>
                <input
                  className="mt-3 w-full accent-blue-600"
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={severity}
                  onChange={(event) => setSeverity(Number(event.target.value))}
                />
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold" style={{ color: 'var(--slate)' }}>
                  Duration
                </p>
                <div className="grid grid-cols-4 gap-2">
                  {[30, 60, 90, 120].map((minutes) => (
                    <button
                      type="button"
                      key={minutes}
                      onClick={() => setDuration(minutes)}
                      className={`rounded-lg border px-2 py-2 text-xs font-mono ${duration === minutes ? 'border-blue-400 bg-blue-50 text-blue-900' : 'border-slate-200 bg-white text-slate-600'}`}
                    >
                      {minutes} min
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleDeclare}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white"
                >
                  <Send className="h-4 w-4" />
                  PUBLISH GRID EVENT
                </button>
                <button
                  type="button"
                  onClick={handleCancel}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700"
                >
                  <XCircle className="h-4 w-4" />
                  CANCEL EVENT
                </button>
              </div>

              {lastActionMessage && (
                <p className="rounded-lg bg-blue-50 p-3 text-xs text-blue-900">
                  {lastActionMessage}
                </p>
              )}
            </div>
          </section>

          <section className="card p-6 lg:col-span-5">
            <p className="eyebrow">Live prototype node</p>
            <h3 className="font-semibold" style={{ color: 'var(--navy)' }}>
              Edge-confirmed runtime
            </h3>

            <div className="mt-4 space-y-3 text-xs">
              <Row
                icon={<Cpu className="h-4 w-4" />}
                label="House"
                value={homeState.house_id}
              />
              <Row
                icon={<Radio className="h-4 w-4" />}
                label="Current severity"
                value={homeState.grid_peak_severity.toFixed(2)}
              />
              <Row
                icon={<Zap className="h-4 w-4" />}
                label="Estimated household load"
                value={`${homeState.aggregate_power_kw.toFixed(3)} kW`}
              />
              <Row
                icon={<Cpu className="h-4 w-4" />}
                label="Registered runtime appliances"
                value={String(homeState.appliances.length)}
              />
            </div>

            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-600">
              Fleet-level homes responding, feeder MW, transformer MVA and grid frequency are
              not shown because this prototype does not receive live substation telemetry.
            </div>

            <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 p-3">
              <div className="text-[11px] text-blue-700">Runtime event state</div>
              <div className="mt-1 font-mono text-sm font-bold text-blue-950">
                {peakEvent.is_active ? 'PEAK ACTIVE' : 'NORMAL'}
              </div>
              <div className="mt-1 text-[11px] text-blue-700">
                Source: edge/runtime telemetry
              </div>
            </div>
          </section>
        </div>
      )}

      {activeTab !== 'dispatch' && (
        <section className="card p-6">
          <p className="eyebrow">Live telemetry boundary</p>
          <h3 className="font-semibold" style={{ color: 'var(--navy)' }}>
            No live feeder telemetry connected
          </h3>
          <p className="mt-2 text-sm" style={{ color: 'var(--slate)' }}>
            This build has household/Pi telemetry only. Feeder-wide analytics are intentionally
            not populated with demo numbers.
          </p>
        </section>
      )}
    </div>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 py-2.5">
      <span className="flex items-center gap-2 text-slate-500">
        {icon}
        {label}
      </span>
      <strong className="font-mono text-[#17365D]">{value}</strong>
    </div>
  );
}
