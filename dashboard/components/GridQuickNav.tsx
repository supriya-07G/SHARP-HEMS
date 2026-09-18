'use client';

import React from 'react';

export type GridTab = 'dispatch' | 'feeder' | 'history';

interface GridQuickNavProps {
  activeTab: GridTab;
  onTabChange: (tab: GridTab) => void;
  isPeakActive: boolean;
  severity: number;
}

const TABS: Array<{
  id: GridTab;
  label: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    id: 'dispatch',
    label: 'Event Dispatch',
    description: 'Declare grid peak event',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'feeder',
    label: 'Feeder Telemetry',
    description: '431 enrolled smart homes',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 17c2.5 0 2.5-8 5-8s2.5 8 5 8 2.5-8 5-8 2.5 4 3 4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'history',
    label: 'Signal Logs',
    description: 'Broadcasts & cancels',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="12 6 12 12 16 14" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export function GridQuickNav({
  activeTab,
  onTabChange,
  isPeakActive,
  severity,
}: GridQuickNavProps) {
  return (
    <nav className="mb-6 rounded-[20px] p-2"
         style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' }}>
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <div className="hidden sm:flex items-center px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-[var(--slate-soft)]">
          Grid Quick Links
        </div>

        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`flex flex-1 min-w-[140px] sm:min-w-0 items-center justify-between gap-2.5 rounded-[14px] px-3.5 py-2.5 transition-all text-left ${
                isActive ? 'shadow-sm' : 'hover:bg-slate-50'
              }`}
              style={{
                background: isActive ? 'linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%)' : 'transparent',
                color: isActive ? '#ffffff' : 'var(--navy)',
              }}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="shrink-0 opacity-90" style={{ color: isActive ? '#ffffff' : 'var(--primary)' }}>
                  {tab.icon}
                </span>
                <div className="min-w-0">
                  <span className="block text-[13px] font-semibold leading-tight truncate">
                    {tab.label}
                  </span>
                  <span className="block text-[10.5px] truncate opacity-80"
                        style={{ color: isActive ? '#dbeafe' : 'var(--slate)' }}>
                    {tab.description}
                  </span>
                </div>
              </div>

              {tab.id === 'dispatch' && (
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  isPeakActive ? 'bg-rose-500 text-white' : 'bg-emerald-500 text-white'
                }`}>
                  {isPeakActive ? `PEAK (${severity.toFixed(2)})` : 'NORMAL'}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
