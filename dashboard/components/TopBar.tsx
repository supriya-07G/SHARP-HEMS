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

import { HomeIllustration } from '@/components/HomeIllustration';
import { Role, ROLES } from '@/lib/roles';

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
  const stale = !live || dataAgeSeconds > 1800;
  const date = timestampIst.slice(0, 10);
  const time = timestampIst.slice(11, 16);

  return (
    <header className="mb-6">
      {/* Status row */}
      <div className="mb-3.5 flex flex-wrap items-center justify-end gap-2.5">
        <span className="chip chip-slate">{date} · {time} IST</span>

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
          className="rounded-[11px] px-3 py-1.5 text-[12.5px] font-semibold"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            color: 'var(--navy)',
          }}
        >
          {ROLES.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>

        <span className="hidden sm:inline-flex chip chip-blue" title="House id">
          {houseId}
        </span>
      </div>

      {/* Hero band. The artwork is clipped by the band, so it can never
          collide with the copy however the viewport changes. */}
      <div
        className="relative overflow-hidden rounded-[22px] px-6 py-6 sm:px-8 sm:py-8 xl:min-h-[176px]"
        style={{
          background:
            'linear-gradient(112deg,#eaf3ff 0%,#f4f9ff 46%,#edf7f1 100%)',
          border: '1px solid #e3edf8',
        }}
      >
        <HomeIllustration className="pointer-events-none absolute bottom-0 right-0 hidden h-[172px] w-[392px] xl:block" />

        <div className="relative max-w-[540px]">
          <p className="eyebrow">Guntur · APCPDCL</p>
          <h1
            className="mt-2 text-[30px] sm:text-[36px] font-semibold tracking-tight leading-[1.08]"
            style={{ color: 'var(--navy)' }}
          >
            {greeting(timestampIst)}
          </h1>
          <p className="mt-2.5 text-[14px] leading-relaxed" style={{ color: 'var(--slate)' }}>
            {SUBTITLE[role]}
          </p>
        </div>
      </div>
    </header>
  );
}
