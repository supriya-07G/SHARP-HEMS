'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActionLevel,
  CommandAck,
  HomeState,
  Intent,
  PeakEvent,
  SystemConnectionStatus,
  WeatherData,
} from './contracts';
import {
  connectFeed,
  PiAck,
  RuntimeHealth,
} from './mqtt';

export interface LiveLoadPoint {
  time: string;
  sharpKw: number;
  baselineKw: number;
  gridPeakSeverity: number;
}

async function sendOverrideToPi(
  houseId: string,
  applianceId: string,
  level: ActionLevel,
  clientLatencyMs?: number,
): Promise<{
  accepted: boolean;
  published: boolean;
  command?: { override_id: string };
  error?: string;
}> {
  const res = await fetch('/api/override', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      house_id: houseId,
      appliance_id: applianceId,
      requested_level: level,
      client_latency_ms: clientLatencyMs ?? null,
    }),
  });

  return res.json();
}

async function publishGridEvent(
  action: 'declare' | 'cancel',
  severity?: number,
  durationMinutes?: number,
) {
  const res = await fetch('/api/grid-event', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      action,
      severity,
      duration_minutes: durationMinutes,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error ?? 'Grid event publish failed');
  }
}

const EMPTY_PEAK_EVENT: PeakEvent = {
  event_id: '',
  sequence: 0,
  region: 'APCPDCL / Guntur',
  severity: 0,
  declared_at: '',
  expires_at: '',
  reason: 'runtime_state',
  is_active: false,
};

const INITIAL_STATUS: SystemConnectionStatus = {
  status: 'disconnected',
  data_age_seconds: 0,
  broker_endpoint: 'HiveMQ WSS',
  last_verified_at: '',
  is_fallback: false,
};

export interface UseHomeStateReturn {
  homeState: HomeState | null;
  peakEvent: PeakEvent;
  intent: Intent | null;
  systemStatus: SystemConnectionStatus;
  activeScenario: 'normal' | 'peak' | 'outage';
  setScenario: (scenario: 'normal' | 'peak' | 'outage') => void;
  triggerOverride: (
    applianceId: string,
    requestedLevel: ActionLevel,
  ) => Promise<CommandAck>;
  declarePeakEvent: (severity: number, durationMinutes: number) => void;
  cancelPeakEvent: () => void;
  lastAck: CommandAck | null;
  clearLastAck: () => void;
  setWeather: (weather: WeatherData) => void;
  pendingAppliances: Set<string>;
  history: LiveLoadPoint[];
  piHealth: RuntimeHealth | null;
  runtimeHealth: RuntimeHealth | null;
}

function peakFromState(state: HomeState): PeakEvent {
  const severity = Number(state.grid_peak_severity ?? 0);
  return {
    event_id: `runtime-${state.step_id ?? state.timestamp_ist}`,
    sequence: Number(state.step_id ?? 0),
    region: 'APCPDCL / Guntur',
    severity,
    declared_at: state.timestamp_ist,
    expires_at: '',
    reason: severity >= 0.4 ? 'runtime_grid_peak' : 'runtime_normal',
    is_active: severity >= 0.4,
  };
}

function chartPoint(state: HomeState): LiveLoadPoint {
  const when = new Date(state.timestamp_ist);
  const time = Number.isNaN(when.getTime())
    ? state.timestamp_ist
    : when.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Kolkata',
      });

  // No uncontrolled live meter exists in this prototype. Use the current
  // estimated aggregate for both series so we never fabricate a baseline.
  return {
    time,
    sharpKw: Number(state.aggregate_power_kw ?? 0),
    baselineKw: Number(state.aggregate_power_kw ?? 0),
    gridPeakSeverity: Number(state.grid_peak_severity ?? 0),
  };
}

export function useHomeState(): UseHomeStateReturn {
  const [homeState, setHomeState] = useState<HomeState | null>(null);
  const [peakEvent, setPeakEvent] = useState<PeakEvent>(EMPTY_PEAK_EVENT);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [systemStatus, setSystemStatus] =
    useState<SystemConnectionStatus>(INITIAL_STATUS);
  const [lastAck, setLastAck] = useState<CommandAck | null>(null);
  const [pendingAppliances, setPendingAppliances] =
    useState<Set<string>>(new Set());
  const [history, setHistory] = useState<LiveLoadPoint[]>([]);
  const [piHealth, setPiHealth] = useState<RuntimeHealth | null>(null);
  const [runtimeHealth, setRuntimeHealth] =
    useState<RuntimeHealth | null>(null);

  const handleAckRef = useRef<((ack: PiAck) => void) | null>(null);

  const handleAck = useCallback((ack: PiAck) => {
    setPendingAppliances((prev) => {
      const next = new Set(prev);
      next.delete(ack.appliance_id);
      return next;
    });

    if (ack.accepted) {
      setHomeState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          appliances: prev.appliances.map((app) =>
            app.appliance_id === ack.appliance_id
              ? {
                  ...app,
                  level: ack.applied_level as ActionLevel,
                  gpio_state: ack.gpio_state,
                  actuation_verified: true,
                  measured_w: ack.measured_w,
                }
              : app,
          ),
        };
      });
    }

    setLastAck({
      command_id: ack.command_id,
      appliance_id: ack.appliance_id,
      accepted: ack.accepted,
      applied_level: ack.applied_level as ActionLevel,
      rejected_reason: ack.rejected_reason,
      gpio_state: ack.gpio_state,
      measured_w: ack.measured_w,
      verification: ack.verification,
      acked_at: ack.acked_at,
      latency_ms: ack.latency_ms,
      delivery_stage: 'hardware',
    });
  }, []);

  handleAckRef.current = handleAck;

  useEffect(() => {
    const disconnect = connectFeed({
      onFeed: (feed) => {
        setSystemStatus((prev) => ({
          ...prev,
          status:
            feed.status === 'live'
              ? 'connected'
              : feed.status === 'connecting'
                ? 'reconnecting'
                : 'disconnected',
          data_age_seconds: Math.round(feed.dataAgeSeconds),
          last_verified_at:
            feed.status === 'live'
              ? new Date().toISOString()
              : prev.last_verified_at,
          is_fallback: feed.status === 'stale',
        }));

        if (feed.state) {
          setHomeState(feed.state);
          setPeakEvent(peakFromState(feed.state));
          setHistory((prev) => {
            const next = [...prev, chartPoint(feed.state!)];
            return next.slice(-96);
          });
        }

        if (feed.intent) {
          setIntent(feed.intent);
        }
      },
      onAck: (ack) => handleAckRef.current?.(ack),
      onPiHealth: setPiHealth,
      onRuntimeHealth: setRuntimeHealth,
    });

    return disconnect;
  }, []);

  const triggerOverride = useCallback(
    async (
      applianceId: string,
      requestedLevel: ActionLevel,
    ): Promise<CommandAck> => {
      const t0 = Date.now();
      const currentApp = homeState?.appliances.find(
        (item) => item.appliance_id === applianceId,
      );

      if (!homeState) {
        const unavailable: CommandAck = {
          command_id: `runtime-unavailable-${Date.now()}`,
          appliance_id: applianceId,
          accepted: false,
          applied_level: currentApp?.level ?? 0,
          rejected_reason: 'RUNTIME_UNAVAILABLE',
          gpio_state: currentApp?.gpio_state ?? 0,
          measured_w: null,
          verification: 'NO_METER',
          acked_at: new Date().toISOString(),
          latency_ms: Date.now() - t0,
          delivery_stage: 'local',
        };
        setLastAck(unavailable);
        return unavailable;
      }

      let result: {
        accepted: boolean;
        published: boolean;
        command?: { override_id: string };
        error?: string;
      };

      try {
        result = await sendOverrideToPi(
          homeState.house_id,
          applianceId,
          requestedLevel,
        );
      } catch {
        result = {
          accepted: false,
          published: false,
          error: 'BROKER_UNAVAILABLE',
        };
      }

      if (!result.published) {
        const failed: CommandAck = {
          command_id:
            result.command?.override_id ?? `broker-error-${Date.now()}`,
          appliance_id: applianceId,
          accepted: false,
          applied_level: currentApp?.level ?? 0,
          rejected_reason: result.error ?? 'BROKER_UNAVAILABLE',
          gpio_state: currentApp?.gpio_state ?? 0,
          measured_w: null,
          verification: 'NO_METER',
          acked_at: new Date().toISOString(),
          latency_ms: Date.now() - t0,
          delivery_stage: 'local',
        };
        setLastAck(failed);
        return failed;
      }

      setPendingAppliances((prev) => {
        const next = new Set(prev);
        next.add(applianceId);
        return next;
      });

      return {
        command_id:
          result.command?.override_id ?? `dispatched-${Date.now()}`,
        appliance_id: applianceId,
        accepted: true,
        applied_level: requestedLevel,
        rejected_reason: null,
        gpio_state: currentApp?.gpio_state ?? 0,
        measured_w: null,
        verification: 'NO_METER',
        acked_at: new Date().toISOString(),
        latency_ms: Date.now() - t0,
        delivery_stage: 'broker',
      };
    },
    [homeState],
  );

  const declarePeakEvent = useCallback(
    (severity: number, durationMinutes: number) => {
      void publishGridEvent('declare', severity, durationMinutes).catch(
        (error) => console.error('Grid event publish failed:', error),
      );
    },
    [],
  );

  const cancelPeakEvent = useCallback(() => {
    void publishGridEvent('cancel').catch((error) =>
      console.error('Grid event cancel failed:', error),
    );
  }, []);

  // Kept for component compatibility. Scenario controls no longer fabricate
  // local HomeState. Peak/normal requests are sent through the real MQTT path;
  // outage simulation is intentionally not represented as live telemetry.
  const setScenario = useCallback(
    (scenario: 'normal' | 'peak' | 'outage') => {
      if (scenario === 'peak') {
        declarePeakEvent(0.67, 60);
      } else if (scenario === 'normal') {
        cancelPeakEvent();
      } else {
        console.warn(
          'Outage simulation is disabled in live mode; no fake state created.',
        );
      }
    },
    [cancelPeakEvent, declarePeakEvent],
  );

  const activeScenario: 'normal' | 'peak' | 'outage' =
    homeState?.grid_absent
      ? 'outage'
      : (homeState?.grid_peak_severity ?? 0) >= 0.4
        ? 'peak'
        : 'normal';

  const clearLastAck = useCallback(() => setLastAck(null), []);

  // Weather is authoritative only after it returns through the MQTT runtime
  // stream. Do not mutate the displayed HomeState optimistically.
  const setWeather = useCallback((_weather: WeatherData) => undefined, []);

  return {
    homeState,
    peakEvent,
    intent,
    systemStatus,
    activeScenario,
    setScenario,
    triggerOverride,
    declarePeakEvent,
    cancelPeakEvent,
    lastAck,
    clearLastAck,
    setWeather,
    pendingAppliances,
    history,
    piHealth,
    runtimeHealth,
  };
}
