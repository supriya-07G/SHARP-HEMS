'use client';

import React, { useState } from 'react';
import {
  HomeState,
  PeakEvent,
  ActionLevel,
  CommandAck,
} from '@/lib/contracts';

import { PeakEventCard } from './PeakEventCard';
import { PowerChart } from './PowerChart';
import { Panel4Appliances } from './Panel4Appliances';
import { MetricsPanel } from './MetricsPanel';
import { BillPanel } from './BillPanel';
import { PeakAlert } from './PeakAlert';
import { TopQuickNav, FeatureTab } from './TopQuickNav';
import { WeatherCard } from './WeatherCard';
import type { LiveLoadPoint } from '@/lib/useHomeState';

interface ResidentViewProps {
  homeState: HomeState;
  peakEvent: PeakEvent;
  chartData: LiveLoadPoint[];
  onOverride: (
    applianceId: string,
    level: ActionLevel
  ) => Promise<CommandAck>;
  lastAck: CommandAck | null;
  onClearAck: () => void;
  initialTab?: FeatureTab;
  pendingAppliances: Set<string>;
}

export function ResidentView({
  homeState,
  peakEvent,
  chartData,
  onOverride,
  lastAck,
  onClearAck,
  initialTab = 'overview',
  pendingAppliances,
}: ResidentViewProps) {
  const [activeTab, setActiveTab] = useState<FeatureTab>(initialTab);
  const [alertDismissed, setAlertDismissed] = useState(false);
  const [prevEventId, setPrevEventId] = useState(peakEvent.event_id);

  if (prevEventId !== peakEvent.event_id) {
    setPrevEventId(peakEvent.event_id);
    setAlertDismissed(false);
  }

  const protectedCount = homeState.appliances.filter(
    (a) => a.is_necessity && a.occupant_wants
  ).length;

  return (
    <div className="space-y-6">
      {/* Top Quick Links Navigation Bar */}
      <TopQuickNav
        activeTab={activeTab}
        onTabChange={setActiveTab}
        applianceCount={homeState.appliances.length}
        protectedCount={protectedCount}
      />

      {/* Grid Peak Notice alert stays visible on all tabs if active */}
      {peakEvent.is_active && !alertDismissed && (
        <PeakAlert
          leadTimeMinutes={15}
          severity={homeState.grid_peak_severity}
          affected={homeState.appliances.filter(
            (a) => !a.is_necessity && a.level === 0
          )}
          onKeepOn={(applianceId, latencyMs) => {
            void onOverride(applianceId, 1 as ActionLevel);
            void latencyMs;
          }}
          onDismiss={() => setAlertDismissed(true)}
        />
      )}

      {/* ----------------- TAB 1: OVERVIEW ----------------- */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <WeatherCard weather={homeState.weather} />

          <PeakEventCard peakEvent={peakEvent} />

          {/* Quick Action Navigation Tiles */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div
              onClick={() => setActiveTab('appliances')}
              className="cursor-pointer rounded-[18px] p-5 transition-all hover:scale-[1.01] hover:shadow-md"
              style={{
                background: 'linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%)',
                border: '1px solid #d0e2ff',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="tile" style={{ background: '#dbeafe', color: '#1d4ed8' }}>
                  ⚡
                </span>
                <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full" style={{ background: '#dbeafe', color: '#1e40af' }}>
                  {homeState.appliances.length} Appliances
                </span>
              </div>
              <h3 className="mt-3 font-semibold text-[15px]" style={{ color: 'var(--navy)' }}>
                Appliance & Load Control
              </h3>
              <p className="mt-1 text-[12px]" style={{ color: 'var(--slate)' }}>
                Manage individual appliances, switch overrides, and inspect shield status.
              </p>
              <span className="mt-3 inline-flex items-center text-[12px] font-semibold" style={{ color: '#2563eb' }}>
                Open Controls &rarr;
              </span>
            </div>

            <div
              onClick={() => setActiveTab('billing')}
              className="cursor-pointer rounded-[18px] p-5 transition-all hover:scale-[1.01] hover:shadow-md"
              style={{
                background: 'linear-gradient(135deg, #ffffff 0%, #f4fbf7 100%)',
                border: '1px solid #d1f2e2',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="tile" style={{ background: '#d1fae5', color: '#047857' }}>
                  💳
                </span>
                <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full" style={{ background: '#d1fae5', color: '#065f46' }}>
                  ₹{homeState.marginal_tariff_inr_kwh.toFixed(2)}/kWh
                </span>
              </div>
              <h3 className="mt-3 font-semibold text-[15px]" style={{ color: 'var(--navy)' }}>
                Billing & Tariff Estimate
              </h3>
              <p className="mt-1 text-[12px]" style={{ color: 'var(--slate)' }}>
                APCPDCL domestic tariff calculator and monthly energy usage breakdown.
              </p>
              <span className="mt-3 inline-flex items-center text-[12px] font-semibold" style={{ color: '#059669' }}>
                View Tariff & Costs &rarr;
              </span>
            </div>

            <div
              onClick={() => setActiveTab('analytics')}
              className="cursor-pointer rounded-[18px] p-5 transition-all hover:scale-[1.01] hover:shadow-md"
              style={{
                background: 'linear-gradient(135deg, #ffffff 0%, #fdf8f0 100%)',
                border: '1px solid #fce8cd',
              }}
            >
              <div className="flex items-center justify-between">
                <span className="tile" style={{ background: '#fef3c7', color: '#b45309' }}>
                  📊
                </span>
                <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full" style={{ background: '#fef3c7', color: '#92400e' }}>
                  {homeState.aggregate_power_kw.toFixed(2)} kW live
                </span>
              </div>
              <h3 className="mt-3 font-semibold text-[15px]" style={{ color: 'var(--navy)' }}>
                Power Profile & Analytics
              </h3>
              <p className="mt-1 text-[12px]" style={{ color: 'var(--slate)' }}>
                Inspect the runtime demand samples received since this dashboard was opened.
              </p>
              <span className="mt-3 inline-flex items-center text-[12px] font-semibold" style={{ color: '#d97706' }}>
                View Analytics &rarr;
              </span>
            </div>
          </div>

          <PowerChart
            data={chartData}
            sanctionedLoadKw={homeState.sanctioned_load_kw}
          />
        </div>
      )}

      {/* ----------------- TAB 2: APPLIANCES ----------------- */}
      {activeTab === 'appliances' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold" style={{ color: 'var(--navy)' }}>
                Appliance Shedding & Shield Controls
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--slate)' }}>
                Protected necessity loads will never pause. Luxury appliances pause during peak grid events.
              </p>
            </div>
          </div>

          <Panel4Appliances
            appliances={homeState.appliances}
            onOverride={onOverride}
            lastAck={lastAck}
            onClearAck={onClearAck}
            pendingAppliances={pendingAppliances}
          />
        </div>
      )}

      {/* ----------------- TAB 3: BILLING ----------------- */}
      {activeTab === 'billing' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold" style={{ color: 'var(--navy)' }}>
                Tariff & Monthly Billing Estimate
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--slate)' }}>
                Calculated according to APCPDCL domestic energy tariff rules for Guntur.
              </p>
            </div>
          </div>

          <BillPanel
            monthToDateKwh={homeState.month_to_date_kwh}
            sanctionedLoadKw={homeState.sanctioned_load_kw}
          />
        </div>
      )}

      {/* ----------------- TAB 4: ANALYTICS ----------------- */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold" style={{ color: 'var(--navy)' }}>
                Power Profile & Grid Performance
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--slate)' }}>
                Live runtime demand history and offline validation metrics.
              </p>
            </div>
          </div>

          <PowerChart
            data={chartData}
            sanctionedLoadKw={homeState.sanctioned_load_kw}
          />

          <MetricsPanel />
        </div>
      )}
    </div>
  );
}