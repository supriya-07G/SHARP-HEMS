'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useHomeState } from '@/lib/useHomeState';
import { DEFAULT_ROLE, ROLE_PATH, Role } from '@/lib/roles';
import { Sidebar } from '@/components/Sidebar';
import { TopBar } from '@/components/TopBar';
import { StatCard } from '@/components/StatCard';
import { SystemStatus } from '@/components/SystemStatus';
import { ResidentView } from '@/components/ResidentView';
import { GridController } from '@/components/GridController';
import { TechnicalView } from '@/components/TechnicalView';
import { FeatureTab } from '@/components/TopQuickNav';
import { GridTab } from '@/components/GridQuickNav';
import { TechTab } from '@/components/TechQuickNav';

const ICON = {
  bolt: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" aria-hidden>
      <path d="M13 2 4.5 13H11l-1 9 8.5-11H12l1-9Z" strokeLinecap="round"
            strokeLinejoin="round" />
    </svg>
  ),
  shield: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" aria-hidden>
      <path d="M12 3l7 3v5.5c0 4.3-2.9 8.1-7 9.5-4.1-1.4-7-5.2-7-9.5V6l7-3Z"
            strokeLinecap="round" strokeLinejoin="round" />
      <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  grid: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" aria-hidden>
      <path d="M3 17c2.5 0 2.5-8 5-8s2.5 8 5 8 2.5-8 5-8 2.5 4 3 4"
            strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  rupee: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" aria-hidden>
      <path d="M7 4h10M7 9h10M15 4c0 4-3 5-8 5l8 10" strokeLinecap="round"
            strokeLinejoin="round" />
    </svg>
  ),
};

interface Props {
  initialRole?: Role;
  initialTab?: FeatureTab | GridTab | TechTab;
}

export function DashboardShell({ initialRole = DEFAULT_ROLE, initialTab }: Props) {
  const router = useRouter();
  const [role, setRole] = useState<Role>(initialRole);

  const changeRole = (next: Role) => {
    setRole(next);
    router.push(ROLE_PATH[next], { scroll: false });
  };

  const {
    homeState,
    peakEvent,
    systemStatus,
    activeScenario,
    setScenario,
    triggerOverride,
    declarePeakEvent,
    cancelPeakEvent,
    lastAck,
    clearLastAck,
    pendingAppliances,
    history,
    piHealth,
    runtimeHealth,
  } = useHomeState();

  if (!homeState) {
    return (
      <div className="flex min-h-screen" style={{ background: 'var(--page)' }}>
        <Sidebar role={role} onRoleChange={changeRole} />
        <main className="flex-1 px-4 py-6 sm:px-7 lg:px-9">
          <div className="mx-auto max-w-[1180px]">
            <section className="card p-8">
              <p className="eyebrow">Live runtime</p>
              <h1 className="mt-1 text-xl font-bold" style={{ color: 'var(--navy)' }}>
                Waiting for Raspberry Pi telemetry
              </h1>
              <p className="mt-2 max-w-2xl text-sm" style={{ color: 'var(--slate)' }}>
                No household values are shown until a retained
                <code className="mx-1">home/&lt;house&gt;/runtime</code>
                message arrives from the SHARP runtime bridge.
              </p>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--slate-soft)' }}>MQTT</div>
                  <div className="mt-1 font-mono text-sm" style={{ color: 'var(--navy)' }}>
                    {systemStatus.status}
                  </div>
                </div>
                <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--slate-soft)' }}>Pi</div>
                  <div className="mt-1 font-mono text-sm" style={{ color: 'var(--navy)' }}>
                    {piHealth?.status ?? 'waiting'}
                  </div>
                </div>
                <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--slate-soft)' }}>Runtime bridge</div>
                  <div className="mt-1 font-mono text-sm" style={{ color: 'var(--navy)' }}>
                    {runtimeHealth?.status ?? 'waiting'}
                  </div>
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    );
  }

  const appliances = homeState.appliances ?? [];
  const protectedNow = appliances.filter((a) => a.is_necessity && a.occupant_wants);
  const shedNow = appliances.filter((a) => a.level === 0 && a.peak_locked_out);
  const live = systemStatus.status === 'connected';

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--page)' }}>
      <Sidebar role={role} onRoleChange={changeRole} />

      <div className="flex-1 min-w-0 px-4 py-6 sm:px-7 lg:px-9">
        <div className="mx-auto max-w-[1180px]">
          <TopBar
            role={role}
            houseId={homeState.house_id}
            timestampIst={homeState.timestamp_ist}
            live={live}
            dataAgeSeconds={systemStatus.data_age_seconds}
            onRoleChange={changeRole}
          />

          <section className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Using now"
              value={homeState.aggregate_power_kw.toFixed(3)}
              unit="kW"
              tone="blue"
              icon={ICON.bolt}
              chip={{ text: `of ${homeState.sanctioned_load_kw} kW sanctioned` }}
              note="estimated from GPIO + catalogue"
            />
            <StatCard
              label="Protected"
              value={String(protectedNow.length)}
              unit={protectedNow.length === 1 ? 'appliance' : 'appliances'}
              tone="mint"
              icon={ICON.shield}
              chip={{ text: 'shielded', tone: 'mint' }}
            />
            <StatCard
              label="Grid"
              value={peakEvent.is_active ? 'Peak' : 'Normal'}
              tone={peakEvent.is_active ? 'yellow' : 'slate'}
              icon={ICON.grid}
              chip={{
                text: `severity ${homeState.grid_peak_severity.toFixed(2)}`,
                tone: peakEvent.is_active ? 'yellow' : 'slate',
              }}
              note={shedNow.length ? `${shedNow.length} paused` : undefined}
            />
            <StatCard
              label="Tariff now"
              value={`₹${homeState.marginal_tariff_inr_kwh.toFixed(2)}`}
              unit="/kWh"
              tone="slate"
              icon={ICON.rupee}
              chip={{ text: `${homeState.month_to_date_kwh.toFixed(0)} kWh this month` }}
              note="model/config-derived estimate"
            />
          </section>

          <div className="mt-4">
            <SystemStatus
              status={systemStatus}
              houseId={homeState.house_id}
              gridAbsent={homeState.grid_absent}
              operatingMode={homeState.operating_mode}
            />
          </div>

          <div className="mt-4 space-y-4">
            {role === 'resident' && (
              <ResidentView
                homeState={homeState}
                peakEvent={peakEvent}
                chartData={history}
                onOverride={triggerOverride}
                lastAck={lastAck}
                onClearAck={clearLastAck}
                initialTab={initialTab as FeatureTab}
                pendingAppliances={pendingAppliances}
              />
            )}

            {role === 'grid' && (
              <GridController
                peakEvent={peakEvent}
                homeState={homeState}
                onDeclarePeak={declarePeakEvent}
                onCancelPeak={cancelPeakEvent}
                initialTab={initialTab as GridTab}
              />
            )}

            {role === 'technical' && (
              <TechnicalView
                homeState={homeState}
                peakEvent={peakEvent}
                activeScenario={activeScenario}
                onScenarioChange={setScenario}
                initialTab={initialTab as TechTab}
              />
            )}
          </div>

          <footer className="mt-8 pt-5 text-[11px] leading-relaxed"
                  style={{ borderTop: '1px solid var(--border)', color: 'var(--slate-soft)' }}>
            <p>
              SHARP · prototype. GPIO/actuation state is hardware-confirmed when
              <strong> actuation_verified</strong> is true. Appliance wattages and aggregate
              power are estimates because no PZEM/meter is fitted; <code>measured_w</code>
              remains null.
            </p>
          </footer>
        </div>
      </div>
    </div>
  );
}
