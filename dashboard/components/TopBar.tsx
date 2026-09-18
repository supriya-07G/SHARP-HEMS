'use client';

/**
 * The top of every view: status chips, then a hero band carrying the greeting
 * and the house artwork.
 *
 * The chips sit on their own row. Sharing one with the greeting put them on
 * top of the artwork and left both looking cramped.
 *
 * The live/stale indicator is not decoration. A dashboard that renders stale
 * data as live is worse than one showing nothing, because nobody knows to
 * distrust it - so the age is shown as soon as the feed falls behind.
 */

import { useState } from 'react';
import { HomeIllustration } from '@/components/HomeIllustration';
import { Role, ROLES } from '@/lib/roles';
import { Menu, X } from 'lucide-react';

interface Props {
  role: Role;
  houseId: string;
  timestampIst: string;
  live: boolean;
  dataAgeSeconds: number;
  onRoleChange: (role: Role) => void;
}

function greeting(iso: string) {
  const hour = Number(iso.slice(11, 13));
  if (Number.isNaN(hour)) return 'Welcome';
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

const SUBTITLE: Record<Role, string> = {
  resident: 'Your fan, light and fridge stay on — whatever the grid is doing.',
  grid: 'Declare an event. Luxury pauses; nobody goes dark.',
  technical: 'The model, the live state, and the settings behind the demo.',
};

export function TopBar({
  role, houseId, timestampIst, live, dataAgeSeconds, onRoleChange,
}: Props) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const stale = !live || dataAgeSeconds > 1800;
  const date = timestampIst.slice(0, 10);
  const time = timestampIst.slice(11, 16);

  return (
    <header className="mb-6">
      {/* Mobile Top Brand Bar (Visible on phones & tablets) */}
      <div className="flex lg:hidden items-center justify-between mb-4 pb-3 border-b border-sky-200">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white font-extrabold shadow-sm">
            S
          </span>
          <span className="text-xl font-extrabold text-[#0f172a] tracking-tight">
            SHARP
          </span>
        </div>

        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-sky-200 text-slate-800 font-semibold text-xs shadow-sm cursor-pointer"
        >
          {mobileMenuOpen ? <X className="h-4 w-4 text-rose-600" /> : <Menu className="h-4 w-4 text-blue-600" />}
          <span>Menu</span>
        </button>
      </div>

      {/* Mobile Role Navigation Drawer Modal */}
      {mobileMenuOpen && (
        <div className="lg:hidden mb-4 rounded-2xl bg-white p-4 border border-blue-200 shadow-md space-y-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
            Switch Dashboard Role
          </p>
          <div className="grid grid-cols-1 gap-2">
            {ROLES.map((r) => {
              const active = role === r.id;
              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => {
                    onRoleChange(r.id);
                    setMobileMenuOpen(false);
                  }}
                  className={`flex items-center justify-between p-3 rounded-xl border text-left cursor-pointer transition-all ${
                    active ? 'bg-blue-50 border-blue-400 text-blue-900 font-bold' : 'bg-slate-50 border-slate-200 text-slate-700'
                  }`}
                >
                  <div>
                    <span className="block text-sm">{r.label}</span>
                    <span className="block text-[11px] text-slate-500 font-normal">{r.description}</span>
                  </div>
                  {active && <span className="text-xs font-bold text-blue-600">Active</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Status row */}
      <div className="mb-3.5 flex flex-wrap items-center justify-between sm:justify-end gap-2 text-xs">
        <span className="chip chip-slate">{date} · {time} IST</span>

        <div className="flex items-center gap-2">
          <span className={`chip ${stale ? 'chip-yellow' : 'chip-mint'}`}>
            <span className="dot"
                  style={{ background: stale ? 'var(--yellow)' : 'var(--mint)' }} />
            {stale
              ? dataAgeSeconds > 60
                ? `${Math.round(dataAgeSeconds / 60)} min old`
                : 'stale'
              : 'live'}
          </span>

          <label className="sr-only" htmlFor="role">View as</label>
          <select
            id="role"
            value={role}
            onChange={(e) => onRoleChange(e.target.value as Role)}
            className="rounded-[11px] px-2.5 py-1.5 text-[12px] font-semibold bg-white border border-slate-300 text-slate-800"
          >
            {ROLES.map((r) => (
              <option key={r.id} value={r.id}>{r.label}</option>
            ))}
          </select>

          <span className="hidden sm:inline-flex chip chip-blue" title="House id">
            {houseId}
          </span>
        </div>
      </div>

      {/* Hero band */}
      <div
        className="relative overflow-hidden rounded-[24px] px-5 py-5 sm:px-8 sm:py-8 xl:min-h-[176px] shadow-sm"
        style={{
          background:
            'linear-gradient(135deg, #dbeafe 0%, #eff6ff 50%, #e0f2fe 100%)',
          border: '1px solid #bfdbfe',
        }}
      >
        <HomeIllustration className="pointer-events-none absolute bottom-0 right-0 hidden h-[172px] w-[392px] xl:block opacity-95" />

        <div className="relative max-w-[540px]">
          <p className="eyebrow font-bold text-blue-700">Guntur · APCPDCL</p>
          <h1
            className="mt-1.5 text-[24px] sm:text-[38px] font-extrabold tracking-tight leading-[1.1] text-[#0f172a]"
          >
            {greeting(timestampIst)}
          </h1>
          <p className="mt-2 text-[13px] sm:text-[14.5px] font-medium leading-relaxed text-[#334155]">
            {SUBTITLE[role]}
          </p>
        </div>
      </div>
    </header>
  );
}
