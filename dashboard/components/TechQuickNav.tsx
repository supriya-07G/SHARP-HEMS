'use client';

import React from 'react';

export type TechTab = 'policy' | 'notice' | 'telemetry';

interface TechQuickNavProps {
  activeTab: TechTab;
  onTabChange: (tab: TechTab) => void;
  leadTimeMinutes: number;
}

const TABS: Array<{
  id: TechTab;
  label: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    id: 'policy',
    label: 'BDQ Policy Model',
    description: '50,133 params & zero illegal actions',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="3" width="20" height="14" rx="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="8" y1="21" x2="16" y2="21" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="17" x2="12" y2="21" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'notice',
    label: 'Lead Time & Notice',
    description: 'Bounded 5-15 min resident notice',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="12 6 12 12 16 14" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'telemetry',
    label: 'Live Pi Telemetry',
    description: 'Pi beliefs & thermal model',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export function TechQuickNav({
  activeTab,
  onTabChange,
  leadTimeMinutes,
}: TechQuickNavProps) {
  return (
    <nav className="mb-6 rounded-[20px] p-2"
         style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' }}>
      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
        <div className="hidden sm:flex items-center px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-[var(--slate-soft)]">
          Technical Quick Links
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
                background: isActive ? 'linear-gradient(135deg, #0f172a 0%, #334155 100%)' : 'transparent',
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
                        style={{ color: isActive ? '#cbd5e1' : 'var(--slate)' }}>
                    {tab.description}
                  </span>
                </div>
              </div>

              {tab.id === 'notice' && (
                <span className="shrink-0 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-800">
                  {leadTimeMinutes} min
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
