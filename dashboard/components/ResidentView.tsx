'use client';

import React from 'react';
import {
  Zap,
  Activity,
  Thermometer,
  CloudSun,
  Calendar,
  IndianRupee,
} from 'lucide-react';

import {
  HomeState,
  PeakEvent,
  ActionLevel,
  CommandAck,
} from '@/lib/contracts';

import { StatCard } from './StatCard';
import { PeakEventCard } from './PeakEventCard';
import { PowerChart } from './PowerChart';
import { Panel4Appliances } from './Panel4Appliances';
import { MetricsPanel } from './MetricsPanel';
import { LoadProfilePoint } from '@/lib/mockState';

interface ResidentViewProps {
  homeState: HomeState;
  peakEvent: PeakEvent;
  chartData: LoadProfilePoint[];
  onOverride: (
    applianceId: string,
    level: ActionLevel
  ) => Promise<CommandAck>;
  lastAck: CommandAck | null;
  onClearAck: () => void;
}

export function ResidentView({
  homeState,
  peakEvent,
  chartData,
  onOverride,
  lastAck,
  onClearAck,
}: ResidentViewProps) {
  const isPeakActive =
    homeState.grid_peak_severity >= 0.4 ||
    peakEvent.is_active;

  const loadPercentage =
    (homeState.aggregate_power_kw /
      homeState.sanctioned_load_kw) *
    100;

  return (
    <div className="space-y-6">

      {/* The headline numbers now live in the page shell, above the role
          views, so they stay put when you switch roles. Six near-duplicate
          cards here was one row too many. */}

      {/* =========================================================
          2. PEAK EVENT
      ========================================================= */}
      <PeakEventCard peakEvent={peakEvent} />

      {/* =========================================================
          3. POWER PROFILE
      ========================================================= */}
      <PowerChart
        data={chartData}
        sanctionedLoadKw={homeState.sanctioned_load_kw}
      />

      {/* =========================================================
          4. APPLIANCES
      ========================================================= */}
      <Panel4Appliances
        appliances={homeState.appliances}
        onOverride={onOverride}
        lastAck={lastAck}
        onClearAck={onClearAck}
      />

      {/* =========================================================
          5. PERFORMANCE METRICS
      ========================================================= */}
      <MetricsPanel />
    </div>
  );
}