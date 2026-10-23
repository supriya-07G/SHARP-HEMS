'use client';

/**
 * The notice a resident gets before luxury loads pause, and their chance to
 * object. Idea book §3.3.
 *
 * THIS IS THE PROJECT'S CORE INTERACTION. The override it collects is not a UI
 * event - it is the training label for the preference reward model, and the
 * LATENCY between the notice appearing and the tap is the graded signal. So it
 * is timed from the moment the notice renders, not from the click.
 *
 * Three phases, all owned by the Pi (home/<house>/grid/warning):
 *
 *   warning   - the countdown to shedding. The deadline comes from the Pi, so
 *               a reload or a second screen shows the same time left.
 *   active    - grid peak: flexible loads not kept on are paused and locked.
 *   household - this home's own peak with no grid peak: the same, here only.
 *
 * Two honesty rules:
 *
 *   The override is a REQUEST, never a command. The Pi's shield decides and may
 *   refuse - during a peak, the luxury circuit has no power to give.
 *
 *   The charge shown is a PROPOSAL under the 2023 Rules. APCPDCL has no
 *   domestic time-of-day rate today, so it is never presented as a bill this
 *   utility would issue.
 */

import { useEffect, useRef, useState } from 'react';
import { ApplianceState } from '@/lib/contracts';
import { PROPOSED_OPT_OUT_INR_PER_EVENT } from '@/lib/billing';
import { SurchargeConfirm } from './SurchargeConfirm';

interface Props {
  phase: 'warning' | 'active' | 'household';
  /** Epoch ms when shedding starts. Null when the Pi gave no deadline. */
  shedAtMs: number | null;
  /** Flexible loads this peak applies to. */
  affected: ApplianceState[];
  /** Appliances the Pi has registered as kept on (billed). */
  keptOnIds: string[];
  severity: number;
  /** Called only after the resident accepts the surcharge. */
  onKeepOn: (applianceId: string, latencyMs: number) => void;
  onDismiss: () => void;
}

function secondsUntil(ms: number | null) {
  return ms === null ? 0 : Math.max(0, Math.ceil((ms - Date.now()) / 1000));
}

export function PeakAlert({
  phase, shedAtMs, affected, keptOnIds, severity, onKeepOn, onDismiss,
}: Props) {
  const shownAt = useRef<number>(0);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [requestedIds, setRequestedIds] = useState<string[]>([]);
  const [confirming, setConfirming] = useState<
    { appliance: ApplianceState; latencyMs: number } | null
  >(null);

  useEffect(() => {
    shownAt.current = Date.now();
  }, [phase]);

  useEffect(() => {
    const update = () => setSecondsLeft(secondsUntil(shedAtMs));
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, [shedAtMs]);

  // A browser notification, where the resident has allowed one. The real
  // system also sends Web Push so the phone rings with no tab open; this is
  // the in-page equivalent for the demo.
  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    const minutes = Math.ceil(secondsUntil(shedAtMs) / 60);
    try {
      new Notification(
        phase === 'warning' ? `Grid peak in ${minutes} minutes`
          : phase === 'household' ? 'Your home is at its peak' : 'Grid peak started',
        {
          body: 'Luxury loads will pause. Your fan, light and fridge stay on.',
          tag: 'sharp-peak',
        },
      );
    } catch {
      /* notification is a courtesy; never let it break the page */
    }
  }, [phase, shedAtMs]);

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
  const ss = String(secondsLeft % 60).padStart(2, '0');
  const name = (a: ApplianceState) => a.display_name ?? a.appliance_id;

  const handleKeep = (a: ApplianceState) => {
    // The latency IS the preference signal. Measure it from when the resident
    // could first have acted, at the tap - not after the confirm dialog.
    // eslint-disable-next-line react-hooks/purity
    const now = Date.now();
    const start = shownAt.current || now;
    setConfirming({ appliance: a, latencyMs: now - start });
  };

  const confirm = () => {
    if (!confirming) return;
    const id = confirming.appliance.appliance_id;
    setRequestedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    onKeepOn(id, confirming.latencyMs);
    setConfirming(null);
  };

  const pausing = affected.filter((a) => !keptOnIds.includes(a.appliance_id));

  return (
    <section
      className="relative overflow-hidden rounded-[18px] p-5"
      style={{ background: 'var(--yellow-tint)', border: '1px solid #f6e3b0' }}
      role="alert"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="tile" style={{
              width: 34, height: 34, borderRadius: 11,
              background: '#fdeec2', color: 'var(--yellow-ink)',
            }}>
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 9v4m0 4h.01M10.3 3.9 2.4 17.5A1.8 1.8 0 0 0 4 20.2h16a1.8 1.8 0 0 0 1.6-2.7L13.7 3.9a1.8 1.8 0 0 0-3.4 0Z"
                      strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
              <p className="text-[15px] font-semibold tabular-nums" style={{ color: 'var(--navy)' }}>
                {phase === 'warning'
                  ? (shedAtMs === null ? 'Grid peak starting soon' : `Grid peak in ${mm}:${ss}`)
                  : phase === 'household'
                    ? 'Household peak in your home'
                    : 'Grid peak in progress'}
              </p>
              <p className="text-[12px]" style={{ color: 'var(--yellow-ink)' }}>
                {phase === 'household'
                  ? 'No grid peak · this home only'
                  : `Severity ${severity.toFixed(2)} · APCPDCL Guntur`}
              </p>
            </div>
          </div>

          <p className="mt-3 text-[13px] leading-relaxed" style={{ color: 'var(--navy)' }}>
            {pausing.length === 0
              ? 'Nothing of yours will pause.'
              : <>{phase === 'warning' ? 'These will pause' : 'Paused and locked until the peak ends'}: <strong>
                  {pausing.map(name).join(', ')}
                </strong>.</>}
            {' '}Your <strong>fan, light and fridge stay on</strong> — the shield
            will not shed an essential load, and nor can the DISCOM.
          </p>
        </div>

        <button type="button" className="btn btn-quiet" onClick={onDismiss}>
          Fine by me
        </button>
      </div>

      {/* Pay to keep appliances running. Opt-out, as Critical Peak Pricing does. */}
      {affected.length > 0 && (
        <div className="mt-4 rounded-[13px] p-3.5"
             style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <p className="text-[12px] font-semibold" style={{ color: 'var(--navy)' }}>
            Keep appliances running through the event?
          </p>
          <p className="mt-0.5 text-[11px]" style={{ color: 'var(--slate)' }}>
            ₹{PROPOSED_OPT_OUT_INR_PER_EVENT.toFixed(2)} per device for this event, added
            only after you confirm.{' '}
            <em>Proposed tariff, not an APCPDCL charge today.</em>
          </p>

          <div className="mt-2.5 flex flex-wrap gap-2">
            {affected.map((a) => {
              const kept = keptOnIds.includes(a.appliance_id);
              const requested = !kept && requestedIds.includes(a.appliance_id);
              return (
                <button
                  key={a.appliance_id}
                  type="button"
                  disabled={kept || requested}
                  className={`btn transition-all ${
                    kept
                      ? 'bg-emerald-600 text-white font-semibold'
                      : 'btn-primary'
                  }`}
                  onClick={() => handleKeep(a)}
                >
                  {kept
                    ? `✓ ${name(a)} kept on · ₹${PROPOSED_OPT_OUT_INR_PER_EVENT.toFixed(2)}`
                    : requested
                      ? `Requesting ${name(a)}…`
                      : `Keep ${name(a)} on`}
                </button>
              );
            })}
          </div>

          {requestedIds.length > 0 && (
            <p className="mt-2.5 text-[11.5px]" style={{ color: 'var(--primary-ink)' }}>
              The Pi decides — a device shows as kept on once the Pi has registered
              it. If the circuit has no power during the event, it will refuse and
              tell you why.
            </p>
          )}
        </div>
      )}

      {confirming && (
        <SurchargeConfirm
          applianceName={name(confirming.appliance)}
          onConfirm={confirm}
          onCancel={() => setConfirming(null)}
        />
      )}
    </section>
  );
}
