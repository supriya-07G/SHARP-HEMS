'use client';

/**
 * The resident's explicit consent before a flexible load runs through a grid
 * peak. Nothing is sent to the Pi until Confirm is pressed.
 *
 * The amount is a PROPOSAL under the 2023 Rules - APCPDCL has no domestic
 * time-of-day rate today - and the dialog says so.
 */

import { useEffect, useRef } from 'react';
import { PROPOSED_OPT_OUT_INR_PER_EVENT } from '@/lib/billing';

interface Props {
  applianceName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SurchargeConfirm({ applianceName, onConfirm, onCancel }: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const amount = `₹${PROPOSED_OPT_OUT_INR_PER_EVENT.toFixed(2)}`;

  // The parent re-renders every second for its countdown; keep the latest
  // handler in a ref so focus is set once and not stolen back each tick.
  const onCancelRef = useRef(onCancel);
  useEffect(() => {
    onCancelRef.current = onCancel;
  });

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancelRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(15, 45, 74, 0.35)' }}
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="surcharge-title"
        aria-describedby="surcharge-body"
        className="card w-full max-w-[420px] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="eyebrow">Peak surcharge</p>
        <h3 id="surcharge-title" className="mt-1 text-[15px] font-semibold"
            style={{ color: 'var(--navy)' }}>
          Keep {applianceName} on during the peak?
        </h3>
        <p id="surcharge-body" className="mt-2 text-[13px] leading-relaxed"
           style={{ color: 'var(--navy)' }}>
          Turning on {applianceName} during peak hours will add a{' '}
          <strong>{amount}</strong> peak surcharge to this month&apos;s bill.
          Do you authorize this charge?
        </p>
        <p className="mt-1.5 text-[11px]" style={{ color: 'var(--slate)' }}>
          <em>Proposed tariff, not an APCPDCL charge today.</em> The Pi still
          decides and may refuse.
        </p>

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button ref={cancelRef} type="button" className="btn btn-quiet" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={onConfirm}>
            Confirm &amp; add {amount} to bill
          </button>
        </div>
      </div>
    </div>
  );
}
