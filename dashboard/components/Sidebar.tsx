'use client';

/**
 * The left rail from the style guide: brand block, role navigation, and a
 * closing note.
 *
 * Navigation here IS the role switch. There is no authentication in this build
 * by decision, so the rail doubles as the demo's way of moving between the
 * resident, the DISCOM and the technical views.
 */

import React from 'react';
import { HomeIllustration } from '@/components/HomeIllustration';
import { Role } from '@/lib/roles';

interface Props {
  role: Role;
  onRoleChange: (role: Role) => void;
}

const NAV: Array<{ id: Role; label: string; hint: string; icon: React.ReactNode }> = [
  {
    id: 'resident',
    label: 'My Home',
    hint: 'Appliances and overrides',
    icon: (
      <path d="M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    id: 'grid',
    label: 'Grid Control',
    hint: 'Declare a peak event',
    icon: (
      <path d="M13 2 4.5 13H11l-1 9 8.5-11H12l1-9Z" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    id: 'technical',
    label: 'Technical',
    hint: 'Model, registry, settings',
    icon: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3m0 14v3M4.2 4.2l2.1 2.1m11.4 11.4 2.1 2.1M2 12h3m14 0h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"
              strokeLinecap="round" />
      </>
    ),
  },
];

export function Sidebar({ role, onRoleChange }: Props) {
  return (
    <aside
      className="hidden lg:flex lg:flex-col w-[248px] shrink-0 px-5 py-6"
      style={{ background: 'linear-gradient(180deg,#eef6ff 0%,#f6faff 55%)' }}
    >
      {/* Brand */}
      <div className="px-2">
        <div className="flex items-center gap-2">
          <span className="text-[22px] font-semibold tracking-tight"
                style={{ color: 'var(--navy)' }}>
            SHARP
          </span>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
               stroke="var(--primary)" strokeWidth="1.8" aria-hidden>
            <path d="M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5"
                  strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <p className="mt-1.5 text-[10px] font-semibold uppercase leading-[1.5]"
           style={{ color: 'var(--slate-soft)', letterSpacing: '0.13em' }}>
          A smarter home<br />for tomorrow
        </p>
      </div>

      {/* Role navigation */}
      <nav className="mt-8 space-y-1" aria-label="Views">
        {NAV.map((item) => {
          const active = role === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onRoleChange(item.id)}
              aria-current={active ? 'page' : undefined}
              className="w-full text-left rounded-[13px] px-3 py-2.5 flex items-center gap-3 transition-colors"
              style={{
                background: active ? 'var(--surface)' : 'transparent',
                boxShadow: active ? 'var(--shadow-sm)' : 'none',
                border: `1px solid ${active ? 'var(--border)' : 'transparent'}`,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                   stroke={active ? 'var(--primary)' : 'var(--slate)'}
                   strokeWidth="1.8" aria-hidden>
                {item.icon}
              </svg>
              <span className="min-w-0">
                <span className="block text-[13.5px] font-semibold leading-tight"
                      style={{ color: active ? 'var(--navy)' : 'var(--slate)' }}>
                  {item.label}
                </span>
                <span className="block text-[10.5px] truncate"
                      style={{ color: 'var(--slate-soft)' }}>
                  {item.hint}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* Closing note. Also the honesty line - it belongs where it is always
          visible, not buried in a footer nobody scrolls to. */}
      <HomeIllustration className="mb-3 h-[86px] w-full opacity-80" />

      <div className="rounded-[16px] p-4"
           style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <p className="text-[13px] font-semibold leading-snug" style={{ color: 'var(--navy)' }}>
          Small changes,<br />big impact
        </p>
        <p className="mt-1.5 text-[11px] leading-relaxed" style={{ color: 'var(--slate)' }}>
          Current for all, whatever the hour.
        </p>
        <p className="mt-3 pt-3 text-[10px] leading-relaxed"
           style={{ color: 'var(--slate-soft)', borderTop: '1px solid var(--border)' }}>
          Prototype. Wattages are simulated; no meter is fitted.
        </p>
      </div>
    </aside>
  );
}
