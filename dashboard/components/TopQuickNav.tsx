'use client';

import React from 'react';

export type FeatureTab = 'overview' | 'appliances' | 'billing' | 'analytics';

interface TopQuickNavProps {
  activeTab: FeatureTab;
  onTabChange: (tab: FeatureTab) => void;
  applianceCount?: number;
  protectedCount?: number;
}

const TABS: Array<{
  id: FeatureTab;
  label: string;
  description: string;
  icon: React.ReactNode;
  badge?: (props: TopQuickNavProps) => string | number | undefined;
}> = [
  {
    id: 'overview',
    label: 'Overview',
    description: 'Grid status & alerts',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="9 22 9 12 15 12 15 22" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'appliances',
    label: 'Appliance Shedding',
    description: 'Control & necessity shield',
    badge: (p) => (p.applianceCount ? `${p.applianceCount}` : undefined),
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18.36 6.64a9 9 0 11-12.73 0" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="2" x2="12" y2="12" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'billing',
    label: 'Billing & Tariff',
    description: 'APCPDCL rates & savings',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="4" width="20" height="16" rx="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="2" y1="10" x2="22" y2="10" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'analytics',
    label: 'Power Analytics',
    description: 'Load profile & metrics',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="18" y1="20" x2="18" y2="10" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="20" x2="12" y2="4" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="6" y1="20" x2="6" y2="14" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export function TopQuickNav({
  activeTab,
  onTabChange,
  applianceCount,
  protectedCount,
}: TopQuickNavProps) {
  return (
    <nav className="mb-6 rounded-[22px] p-2 sm:p-2.5 transition-all shadow-sm overflow-x-auto scrollbar-none"
         style={{ background: 'linear-gradient(180deg, #ffffff 0%, #f0f7ff 100%)', border: '1px solid #bae6fd' }}>
      <div className="flex flex-nowrap sm:flex-wrap items-center gap-1.5 sm:gap-2 min-w-max sm:min-w-0">
        <div className="hidden sm:flex items-center px-3 py-1 text-[11px] font-extrabold uppercase tracking-wider text-sky-700">
          Quick Links
        </div>
        
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const badgeValue = tab.badge ? tab.badge({ activeTab, onTabChange, applianceCount, protectedCount }) : undefined;
          
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`flex flex-1 min-w-[140px] sm:min-w-0 items-center justify-between gap-2.5 rounded-[16px] px-4 py-2.5 transition-all text-left cursor-pointer ${
                isActive ? 'shadow-md scale-[1.01]' : 'hover:bg-sky-50'
              }`}
              style={{
                background: isActive ? 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)' : 'transparent',
                color: isActive ? '#ffffff' : '#0f172a',
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
              
              {badgeValue && (
                <span className="shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-bold"
                      style={{
                        background: isActive ? 'rgba(255,255,255,0.25)' : 'var(--blue-tint)',
                        color: isActive ? '#ffffff' : 'var(--primary-ink)',
                      }}>
                  {badgeValue}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
