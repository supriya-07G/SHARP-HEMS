'use client';

/**
 * The top strip: greeting, date, live/stale indicator, role chip.
 *
 * The connection indicator is not decoration. A dashboard that renders stale
 * data as live is worse than one showing nothing, because nobody knows to
 * distrust it - so the age is shown whenever it is more than a minute old.
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
  resident: 'Your essentials stay on, whatever the grid is doing.',
  grid: 'Declare an event. Luxury pauses; nobody goes dark.',
  technical: 'Model, registry and the settings behind the demo.',
};

export function TopBar({
  role, houseId, timestampIst, live, dataAgeSeconds, onRoleChange,
}: Props) {
  const stale = !live || dataAgeSeconds > 1800;
  const date = timestampIst.slice(0, 10);
  const time = timestampIst.slice(11, 16);

  return (
    <header className="relative mb-6 overflow-hidden xl:min-h-[124px]">
      {/* Quiet decoration. Behind the text, never over it, and gone on small
          screens where the space belongs to content. */}
      <HomeIllustration className="pointer-events-none absolute -top-2 right-0 hidden h-[122px] w-[286px] opacity-75 xl:block" />

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[30px] sm:text-[34px] font-semibold tracking-tight leading-tight"
              style={{ color: 'var(--navy)' }}>
            {greeting(timestampIst)}
          </h1>
          <p className="mt-1 text-[13.5px]" style={{ color: 'var(--slate)' }}>
            {SUBTITLE[role]}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="chip chip-slate">
            {date} · {time} IST
          </span>

          {/* Live or stale, never ambiguous. */}
          <span className={`chip ${stale ? 'chip-yellow' : 'chip-mint'}`}>
            <span className="dot"
                  style={{ background: stale ? 'var(--yellow)' : 'var(--mint)' }} />
            {stale
              ? dataAgeSeconds > 60
                ? `${Math.round(dataAgeSeconds / 60)} min old`
                : 'stale'
              : 'live'}
          </span>

          {/* Role switch. No auth in this build - see lib/roles.ts. */}
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
      </div>
    </header>
  );
}
