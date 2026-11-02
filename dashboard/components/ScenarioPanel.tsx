'use client';

/**
 * Pick the house scenario from the dashboard instead of a Pi terminal.
 *
 * A button only REQUESTS a scenario. The Pi's scenario service applies it and
 * reports back; the panel shows that report as the truth, and says plainly
 * when the service is not reporting (Pi off, or services not running).
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  DEMO_SCENARIOS,
  DemoScenarioId,
  ScenarioActive,
} from '@/lib/scenarios';

interface Props {
  active: ScenarioActive | null;
  onChoose: (scenario: DemoScenarioId) => Promise<string | null>;
}

function istTime(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('en-IN', { hour12: false, timeZone: 'Asia/Kolkata' });
}

export function ScenarioPanel({ active, onChoose }: Props) {
  const [requested, setRequested] = useState<DemoScenarioId | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);

  const appliedMs = active ? Date.parse(active.applied_at) : NaN;
  // The service republishes every `republish_seconds`; three missed rounds
  // (at least a minute) means it is not running.
  const reporting =
    active !== null &&
    !Number.isNaN(appliedMs) &&
    now - appliedMs < Math.max(3 * active.republish_seconds, 60) * 1000;
  const waitingFor =
    requested !== null && active?.scenario !== requested ? requested : null;
  const current = DEMO_SCENARIOS.find((s) => s.id === active?.scenario);
  const chosen = DEMO_SCENARIOS.find((s) => s.id === (waitingFor ?? active?.scenario));

  const choose = async (id: DemoScenarioId) => {
    setSending(true);
    setError(null);
    setRequested(id);
    const failure = await onChoose(id);
    setSending(false);
    if (failure) {
      setError(failure);
      setRequested(null);
    }
  };

  return (
    <section className="card p-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b pb-3"
           style={{ borderColor: 'var(--border)' }}>
        <div>
          <p className="eyebrow">Demo control</p>
          <h3 className="text-lg font-bold" style={{ color: 'var(--navy)' }}>
            House scenario
          </h3>
          <p className="mt-0.5 text-[12px]" style={{ color: 'var(--slate)' }}>
            Chosen here, applied by the scenario service on the Raspberry Pi. No terminal needed.
          </p>
        </div>
        <span className={`px-3 py-1 rounded-full text-xs font-bold ${
          reporting ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
        }`}>
          {reporting ? 'Pi service reporting' : 'Pi service not reporting'}
        </span>
      </div>

      <p className="text-[13px]" style={{ color: 'var(--navy)' }} role="status">
        {reporting && current
          ? <>Active: <strong>{current.label}</strong> · applied {istTime(active!.applied_at)} IST</>
          : active && !reporting
            ? <>Last applied: <strong>{current?.label ?? active.scenario}</strong> at {istTime(active.applied_at)} IST. The service has not reported since.</>
            : 'No report from the scenario service yet.'}
        {waitingFor && (
          <span style={{ color: 'var(--slate)' }}>
            {' '}Waiting for the Pi to apply {DEMO_SCENARIOS.find((s) => s.id === waitingFor)?.label}…
          </span>
        )}
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {DEMO_SCENARIOS.map((s) => {
          const isActive = reporting && active?.scenario === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => void choose(s.id)}
              disabled={sending}
              aria-pressed={isActive}
              className="rounded-[13px] p-3.5 text-left transition-all disabled:cursor-wait disabled:opacity-60"
              style={{
                background: isActive ? 'var(--primary-tint)' : 'var(--surface)',
                border: `1px solid ${isActive ? 'var(--primary)' : 'var(--border)'}`,
              }}
            >
              <span className="block text-[13px] font-semibold" style={{ color: 'var(--navy)' }}>
                {s.label}{isActive ? ' · active' : ''}
              </span>
              <span className="mt-0.5 block text-[11.5px]" style={{ color: 'var(--slate)' }}>
                {s.description}
              </span>
            </button>
          );
        })}
      </div>

      {chosen?.needsGridPeak && (
        <p className="rounded-[11px] p-3 text-[12px]"
           style={{ background: 'var(--yellow-tint)', color: 'var(--navy)' }}>
          This scenario expects a grid peak. Declare it on{' '}
          <Link href="/grid" className="font-semibold underline">Grid Control</Link>
          {' '}(severity 0.60 or more).
        </p>
      )}

      {error && (
        <p className="text-[12px]" style={{ color: 'var(--navy)' }} role="alert">
          Not sent: {error}
        </p>
      )}

      {!reporting && (
        <p className="text-[11.5px]" style={{ color: 'var(--slate)' }}>
          If the Pi is on but the service does not report within a minute, use the SSH
          fallback in <code>docs/RUNBOOK_PEAK_SCENARIOS.md</code>.
        </p>
      )}
    </section>
  );
}
