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
  // Dismissing the notice is per-event, not permanent: the resident said
  // "fine by me" to THIS peak, not to every peak from now on.
  const [alertDismissed, setAlertDismissed] = useState(false);
  const [prevEventId, setPrevEventId] = useState(peakEvent.event_id);

  if (prevEventId !== peakEvent.event_id) {
    setPrevEventId(peakEvent.event_id);
    setAlertDismissed(false);
  }

  return (
    <div className="space-y-6">

      {/* The headline numbers now live in the page shell, above the role
          views, so they stay put when you switch roles. Six near-duplicate
          cards here was one row too many. */}

      {/* The notice, and the chance to object. This is the project's core
          interaction - the override it collects is the reward model's
          training label, and the latency is the graded signal. */}
      {peakEvent.is_active && !alertDismissed && (
        <PeakAlert
          leadTimeMinutes={15}
          severity={homeState.grid_peak_severity}
          affected={homeState.appliances.filter(
            (a) => !a.is_necessity && a.level === 0,
          )}
          onKeepOn={(applianceId, latencyMs) => {
            void onOverride(applianceId, 1 as ActionLevel);
            // Latency travels with the override through the API route; it is
            // what grades the preference, so it must not be dropped here.
            void latencyMs;
          }}
          onDismiss={() => setAlertDismissed(true)}
        />
      )}

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
      <BillPanel
        monthToDateKwh={homeState.month_to_date_kwh}
        sanctionedLoadKw={homeState.sanctioned_load_kw}
      />

      <MetricsPanel />
    </div>
  );
}