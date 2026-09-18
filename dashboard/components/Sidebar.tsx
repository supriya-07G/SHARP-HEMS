'use client';

/**
 * The left rail from the style guide: brand block, role navigation, and a
 * closing note.
 *
 * Navigation here IS the role switch. There is no authentication in this build
 * by decision, so the rail doubles as the demo's way of moving between the
 * resident, the DISCOM and the technical views.
 */

import React, { useState } from 'react';
import { HomeIllustration } from '@/components/HomeIllustration';
import { Role } from '@/lib/roles';
import { ChevronLeft, ChevronRight } from 'lucide-react';

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
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'grid',
    label: 'Grid Control',
    hint: 'Declare a peak event',
    icon: (
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M13 2 4.5 13H11l-1 9 8.5-11H12l1-9Z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'technical',
    label: 'Technical',
    hint: 'Model, registry, settings',
    icon: (
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3m0 14v3M4.2 4.2l2.1 2.1m11.4 11.4 2.1 2.1M2 12h3m14 0h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"
              strokeLinecap="round" />
      </svg>
    ),
  },
];

export function Sidebar({ role, onRoleChange }: Props) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <aside
      className={`hidden lg:flex lg:flex-col shrink-0 py-6 border-r border-[#cbd5e1] transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-[76px] px-3' : 'w-[256px] px-5'
      }`}
      style={{ background: 'linear-gradient(180deg, #e0f2fe 0%, #bae6fd 45%, #f0f9ff 100%)' }}
    >
      {/* Brand & Toggle */}
      <div className={`flex items-center ${isCollapsed ? 'justify-center flex-col gap-3' : 'justify-between px-2'}`}>
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white font-extrabold shadow-sm text-base">
            S
          </span>
          {!isCollapsed && (
            <span className="text-[22px] font-extrabold tracking-tight text-[#0f172a]">
              SHARP
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsCollapsed(!isCollapsed)}
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
          className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/90 text-slate-700 hover:bg-white hover:text-blue-600 transition-all border border-sky-200 shadow-sm cursor-pointer"
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {!isCollapsed && (
        <p className="mt-2 px-2 text-[10px] font-bold uppercase leading-[1.5] text-slate-600 tracking-wider">
          A smarter home<br />for tomorrow
        </p>
      )}

      {/* Role navigation */}
      <nav className="mt-8 space-y-2" aria-label="Views">
        {NAV.map((item) => {
          const active = role === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onRoleChange(item.id)}
              aria-current={active ? 'page' : undefined}
              title={isCollapsed ? item.label : undefined}
              className={`w-full text-left rounded-[16px] transition-all cursor-pointer flex items-center ${
                isCollapsed ? 'justify-center p-3' : 'px-3.5 py-3 gap-3.5'
              }`}
              style={{
                background: active ? 'linear-gradient(135deg, #ffffff 0%, #eff6ff 100%)' : 'transparent',
                boxShadow: active ? '0 4px 14px rgba(37,99,235,0.12)' : 'none',
                border: `1px solid ${active ? '#93c5fd' : 'transparent'}`,
              }}
            >
              <span className={`shrink-0 ${active ? 'text-blue-600' : 'text-slate-600'}`}>
                {item.icon}
              </span>
              
              {!isCollapsed && (
                <span className="min-w-0">
                  <span className="block text-[14px] font-bold leading-tight" style={{ color: active ? '#1e40af' : '#1e293b' }}>
                    {item.label}
                  </span>
                  <span className="block text-[11px] truncate" style={{ color: active ? '#3b82f6' : '#64748b' }}>
                    {item.hint}
                  </span>
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* Footer Illustration & Note */}
      {!isCollapsed && (
        <>
          <HomeIllustration compact className="mb-3 h-[94px] w-full opacity-90" />
          <div className="rounded-[16px] p-4 bg-white border border-[#cbd5e1] shadow-sm">
            <p className="text-[13px] font-bold leading-snug text-[#0f172a]">
              Small changes,<br />big impact
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
              Current for all, whatever the hour.
            </p>
          </div>
        </>
      )}
    </aside>
  );
}
