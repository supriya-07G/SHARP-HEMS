'use client';

import { useState, useCallback, useTransition, useEffect, useRef } from 'react';
import {
  HomeState,
  PeakEvent,
  SystemConnectionStatus,
  ActionLevel,
  CommandAck,
  WeatherData,
} from './contracts';
import {
  NORMAL_HOME_STATE,
  PEAK_ACTIVE_HOME_STATE,
  INITIAL_PEAK_EVENT,
  MOCK_SYSTEM_STATUS,
} from './mockState';
import { connectFeed, PiAck } from './mqtt';

/**
 * Hand the override to the Pi via /api/override (server-side MQTT publish).
 *
 * Returns the parsed JSON body so the caller can extract override_id.
 * Throws on network error or non-OK HTTP status so the caller can show failure.
 * The publish credential stays on the server; it never reaches the browser.
 */
async function sendOverrideToPi(
  houseId: string,
  applianceId: string,
  level: ActionLevel,
  clientLatencyMs?: number,
): Promise<{ accepted: boolean; published: boolean; command?: { override_id: string }; error?: string }> {
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

  // Always parse JSON — even error responses carry a body.
  const json = await res.json();
  return json;
}

export interface UseHomeStateReturn {
  homeState: HomeState;
  peakEvent: PeakEvent;
  systemStatus: SystemConnectionStatus;
  activeScenario: 'normal' | 'peak' | 'outage';
  setScenario: (scenario: 'normal' | 'peak' | 'outage') => void;
  triggerOverride: (
    applianceId: string,
    requestedLevel: ActionLevel
  ) => Promise<CommandAck>;
  declarePeakEvent: (severity: number, durationMinutes: number) => void;
  cancelPeakEvent: () => void;
  lastAck: CommandAck | null;
  clearLastAck: () => void;
  setWeather: (weather: WeatherData) => void;
  /**
   * Set of appliance IDs that have a command in-flight to the Pi.
   * The card must show PENDING and the toggle must be disabled until
   * the Pi publishes an ACK and the ID is removed from this set.
   */
  pendingAppliances: Set<string>;
}

export function useHomeState(): UseHomeStateReturn {
  const [activeScenario, setActiveScenario] = useState<
    'normal' | 'peak' | 'outage'
  >('peak');

  const [homeState, setHomeState] =
    useState<HomeState>(PEAK_ACTIVE_HOME_STATE);

  const [peakEvent, setPeakEvent] =
    useState<PeakEvent>(INITIAL_PEAK_EVENT);

  const [systemStatus] =
    useState<SystemConnectionStatus>(MOCK_SYSTEM_STATUS);

  const [lastAck, setLastAck] =
    useState<CommandAck | null>(null);

  /**
   * Appliance IDs currently waiting for a hardware ACK from the Pi.
   * The card shows PENDING and the toggle is disabled until the Pi responds.
   * State MUST NOT change until the ACK clears this entry.
   */
  const [pendingAppliances, setPendingAppliances] =
    useState<Set<string>>(new Set());

  const [, startTransition] = useTransition();

  // Stable ref so the mount-time MQTT closure always calls the current handler.
  const handleAckRef = useRef<((ack: PiAck) => void) | null>(null);

  // ============================================================
  // PI ACK HANDLER
  // Wired into the MQTT connection below via handleAckRef so that
  // the mount-time closure always reaches the current implementation.
  // Appliance state is ONLY updated here — never before the ACK arrives.
  // ============================================================

  const handleAck = useCallback((ack: PiAck) => {
    // Remove from pending regardless of accepted/rejected.
    setPendingAppliances((prev) => {
      const next = new Set(prev);
      next.delete(ack.appliance_id);
      return next;
    });

    if (ack.accepted) {
      // Hardware confirmed — update level, gpio_state, actuation_verified.
      setHomeState((prev) => ({
        ...prev,
        appliances: prev.appliances.map((app) =>
          app.appliance_id === ack.appliance_id
            ? {
                ...app,
                level: ack.applied_level as ActionLevel,
                gpio_state: ack.gpio_state,
                actuation_verified: true,
                shed_reason:
                  ack.applied_level === 0 ? 'MANUAL_OVERRIDE' : null,
              }
            : app
        ),
      }));
    }
    // If rejected, the previous appliance state is unchanged.

    // Always surface the ACK so the UI can show the banner.
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
    });
  }, []);

  // Keep ref current on every render.
  handleAckRef.current = handleAck;

  // ============================================================
  // MQTT CONNECTION
  // ============================================================

  useEffect(() => {
    console.log('🔌 Starting MQTT connection...');

    const disconnect = connectFeed({
      onFeed: (feed) => {
        console.log('📡 MQTT FEED:', feed);

        // Update dashboard with real HomeState
        // whenever a state message arrives from HiveMQ.
        if (feed.state) {
          console.log('🏠 Received HomeState from MQTT');
          setHomeState(feed.state);
        }

        // Display intent for now.
        // We will wire this into the UI/state later.
        if (feed.intent) {
          console.log('🤖 Received Intent from MQTT:', feed.intent);
        }

        console.log(
          `MQTT status: ${feed.status} | data age: ${feed.dataAgeSeconds.toFixed(
            1
          )}s`
        );
      },
      // Use ref-forwarding so the stable closure always calls current handler.
      onAck: (ack) => handleAckRef.current?.(ack),
    });

    // Disconnect MQTT when the component using this hook unmounts.
    return () => {
      console.log('🔌 Disconnecting MQTT...');
      disconnect();
    };
  }, []);

  // ============================================================
  // SCENARIO CONTROL
  // ============================================================

  const setScenario = useCallback(
    (scenario: 'normal' | 'peak' | 'outage') => {
      startTransition(() => {
        setActiveScenario(scenario);

        if (scenario === 'normal') {
          setHomeState(NORMAL_HOME_STATE);

          setPeakEvent((prev) => ({
            ...prev,
            severity: 0.15,
            is_active: false,
          }));
        } else if (scenario === 'peak') {
          setHomeState(PEAK_ACTIVE_HOME_STATE);

          setPeakEvent({
            ...INITIAL_PEAK_EVENT,
            is_active: true,
            severity: 0.67,
            declared_at: '14:05 IST',
            expires_at: '16:00 IST',
          });
        } else if (scenario === 'outage') {
          // Islanded outage mode
          setHomeState({
            ...PEAK_ACTIVE_HOME_STATE,
            operating_mode: 'islanded_outage',
            grid_absent: true,
            aggregate_power_kw: 0.116,
            appliances: PEAK_ACTIVE_HOME_STATE.appliances.map((app) => {
              if (app.is_necessity) {
                return { ...app, level: 1 };
              }

              return {
                ...app,
                level: 0,
                shed_reason: 'GRID_OUTAGE_BATTERY_RESERVE',
              };
            }),
          });

          setPeakEvent((prev) => ({
            ...prev,
            is_active: false,
          }));
        }
      });
    },
    []
  );

  // ============================================================
  // DECLARE PEAK EVENT
  // ============================================================

  const declarePeakEvent = useCallback(
    (severity: number, durationMinutes: number) => {
      startTransition(() => {
        const now = new Date();

        const declaredStr = '14:05 IST';

        const expireHour =
          14 + Math.floor((5 + durationMinutes) / 60);

        const expireMin = (5 + durationMinutes) % 60;

        const expireStr = `${expireHour
          .toString()
          .padStart(2, '0')}:${expireMin
          .toString()
          .padStart(2, '0')} IST`;

        const newEvent: PeakEvent = {
          event_id: `apcpdcl-${now.getFullYear()}-09-15-${Math.floor(
            Math.random() * 900 + 100
          )}`,
          sequence: 48,
          region: 'APCPDCL / Guntur Urban Sub-12',
          severity,
          declared_at: declaredStr,
          expires_at: expireStr,
          reason: 'system_peak',
          is_active: true,
          homes_responding: 431,
          mw_relieved: Number((severity * 0.42).toFixed(2)),
        };

        setPeakEvent(newEvent);

        // Reflect in home state:
        // if severity > 0.4, shed flexible loads.
        if (severity >= 0.4) {
          setHomeState((prev) => ({
            ...prev,
            grid_peak_severity: severity,
            aggregate_power_kw: 0.145,

            appliances: prev.appliances.map((app) => {
              if (app.is_necessity) {
                return app;
              }

              if (app.appliance_type === 'washing_machine') {
                return {
                  ...app,
                  level: 0,
                  shed_reason: 'PEAK_EVENT',
                  deferred_until: '22:00 IST',
                };
              }

              return {
                ...app,
                level: 0,
                shed_reason: 'GRID_PEAK',
              };
            }),
          }));
        }
      });
    },
    []
  );

  // ============================================================
  // CANCEL PEAK EVENT
  // ============================================================

  const cancelPeakEvent = useCallback(() => {
    startTransition(() => {
      setPeakEvent((prev) => ({
        ...prev,
        is_active: false,
        severity: 0.15,
      }));

      setHomeState(NORMAL_HOME_STATE);
    });
  }, []);

  // ============================================================
  // APPLIANCE OVERRIDE
  // ============================================================

  const triggerOverride = useCallback(
    async (
      applianceId: string,
      requestedLevel: ActionLevel
    ): Promise<CommandAck> => {
      const t0 = Date.now();

      const currentApp = homeState.appliances.find(
        (a) => a.appliance_id === applianceId
      );

      // --------------------------------------------------------
      // Send to Pi via server-side MQTT publish.
      // Throws on network error; returns JSON on HTTP error too.
      // --------------------------------------------------------
      let apiResult: {
        accepted: boolean;
        published: boolean;
        command?: { override_id: string };
        error?: string;
      };

      try {
        apiResult = await sendOverrideToPi(
          homeState.house_id,
          applianceId,
          requestedLevel,
        );
      } catch (netErr) {
        // Network down — can't reach /api/override at all.
        const failedAck: CommandAck = {
          command_id: `net-err-${Date.now()}`,
          appliance_id: applianceId,
          accepted: false,
          applied_level: currentApp?.level ?? 0,
          rejected_reason: 'BROKER_UNAVAILABLE',
          gpio_state: currentApp?.gpio_state ?? 0,
          measured_w: null,
          verification: 'NO_METER',
          acked_at: new Date().toISOString(),
          latency_ms: Date.now() - t0,
        };
        setLastAck(failedAck);
        console.error('❌ Override network error:', netErr);
        return failedAck;
      }

      if (!apiResult.published) {
        // Broker rejected / not configured — leave state unchanged.
        const brokerFailedAck: CommandAck = {
          command_id: apiResult.command?.override_id ?? `api-err-${Date.now()}`,
          appliance_id: applianceId,
          accepted: false,
          applied_level: currentApp?.level ?? 0,
          rejected_reason: apiResult.error ?? 'BROKER_UNAVAILABLE',
          gpio_state: currentApp?.gpio_state ?? 0,
          measured_w: null,
          verification: 'NO_METER',
          acked_at: new Date().toISOString(),
          latency_ms: Date.now() - t0,
        };
        setLastAck(brokerFailedAck);
        console.warn('⚠️ Override not published:', apiResult);
        return brokerFailedAck;
      }

      // --------------------------------------------------------
      // Published to HiveMQ.  Mark the appliance PENDING.
      // The card shows a spinner; the toggle is disabled.
      // Appliance state will only change when the Pi ACK arrives
      // via MQTT and handleAck() is called.
      // --------------------------------------------------------
      setPendingAppliances((prev) => {
        const next = new Set(prev);
        next.add(applianceId);
        return next;
      });

      console.log(
        `⏳ Override dispatched for ${applianceId} → level ${requestedLevel}. Waiting for Pi ACK…`
      );

      // Return a "dispatched" ack.  The real GPIO-confirmed state
      // change arrives asynchronously via handleAck().
      const dispatchedAck: CommandAck = {
        command_id: apiResult.command?.override_id ?? `dispatched-${Date.now()}`,
        appliance_id: applianceId,
        accepted: true,
        applied_level: requestedLevel,
        rejected_reason: null,
        gpio_state: requestedLevel === 0 ? 0 : 1, // optimistic for ack object only
        measured_w: null,
        verification: 'NO_METER',
        acked_at: new Date().toISOString(),
        latency_ms: Date.now() - t0,
      };

      // Do NOT set lastAck here — wait for the real Pi ACK.
      return dispatchedAck;
    },
    [homeState.appliances, homeState.house_id]
  );

  // ============================================================
  // CLEAR ACK
  // ============================================================

  const clearLastAck = useCallback(
    () => setLastAck(null),
    []
  );

  const setWeather = useCallback((weatherData: WeatherData) => {
    startTransition(() => {
      setHomeState((prev) => ({
        ...prev,
        outdoor_temperature_c: weatherData.outdoor_temperature_c,
        weather: weatherData,
      }));
    });
  }, []);

  // ============================================================
  // RETURN
  // ============================================================

  return {
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
    setWeather,
    pendingAppliances,
  };
}