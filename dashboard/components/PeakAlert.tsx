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

interface Props {
  /** Minutes of notice. Set by the technical role, bounded 5-15. */
  leadTimeMinutes: number;
  /** Loads that will pause when the event starts. */
  affected: ApplianceState[];
  severity: number;
  onKeepOn: (applianceId: string, latencyMs: number) => void;
  onDismiss: () => void;
}

export function PeakAlert({
  leadTimeMinutes, affected, severity, onKeepOn, onDismiss,
}: Props) {
  const shownAt = useRef<number>(0);
  const [secondsLeft, setSecondsLeft] = useState(leadTimeMinutes * 60);
  const [prevLeadTime, setPrevLeadTime] = useState(leadTimeMinutes);
  const [chosenIds, setChosenIds] = useState<string[]>([]);

  if (prevLeadTime !== leadTimeMinutes) {
    setPrevLeadTime(leadTimeMinutes);
    setSecondsLeft(leadTimeMinutes * 60);
  }

  useEffect(() => {
    shownAt.current = Date.now();
  }, [leadTimeMinutes]);

  useEffect(() => {
    const t = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  // A browser notification, where the resident has allowed one. The real
  // system also sends Web Push so the phone rings with no tab open; this is
  // the in-page equivalent for the demo.
  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    try {
      new Notification('Grid peak in ' + leadTimeMinutes + ' minutes', {
        body: 'Luxury loads will pause. Your fan, light and fridge stay on.',
        tag: 'sharp-peak',
      });
    } catch {
      /* notification is a courtesy; never let it break the page */
    }
  }, [leadTimeMinutes]);

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
  const ss = String(secondsLeft % 60).padStart(2, '0');

  const handleKeep = (a: ApplianceState) => {
    if (!chosenIds.includes(a.appliance_id)) {
      setChosenIds((prev) => [...prev, a.appliance_id]);
    }
    // The latency IS the preference signal. Measure it from when the resident
    // could first have acted.
    // eslint-disable-next-line react-hooks/purity
    const now = Date.now();
    const start = shownAt.current || now;
    onKeepOn(a.appliance_id, now - start);
  };

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
              <p className="text-[15px] font-semibold" style={{ color: 'var(--navy)' }}>
                Grid peak in {mm}:{ss}
              </p>
              <p className="text-[12px]" style={{ color: 'var(--yellow-ink)' }}>
                Severity {severity.toFixed(2)} · APCPDCL Guntur
              </p>
            </div>
          </div>

          <p className="mt-3 text-[13px] leading-relaxed" style={{ color: 'var(--navy)' }}>
            {affected.length === 0
              ? 'Nothing of yours will pause.'
              : <>These will pause: <strong>
                  {affected.map((a) => a.display_name ?? a.appliance_id).join(', ')}
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
            About ₹{PROPOSED_OPT_OUT_INR_PER_EVENT.toFixed(2)} per device for this event.{' '}
            <em>Proposed tariff, not an APCPDCL charge today.</em>
          </p>

          <div className="mt-2.5 flex flex-wrap gap-2">
            {affected.map((a) => {
              const isChosen = chosenIds.includes(a.appliance_id);
              return (
                <button
                  key={a.appliance_id}
                  type="button"
                  className={`btn transition-all ${
                    isChosen
                      ? 'bg-emerald-600 text-white hover:bg-emerald-700 font-semibold'
                      : 'btn-primary'
                  }`}
                  onClick={() => handleKeep(a)}
                >
                  {isChosen ? `✓ Keeping ${a.display_name ?? a.appliance_id} on` : `Keep ${a.display_name ?? a.appliance_id} on`}
                </button>
              );
            })}
          </div>

          {chosenIds.length > 0 && (
            <p className="mt-2.5 text-[11.5px]" style={{ color: 'var(--primary-ink)' }}>
              Requested for {chosenIds.length} {chosenIds.length === 1 ? 'device' : 'devices'}. The Pi decides — if the circuit has no power during the
              event, it will refuse and tell you why.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
