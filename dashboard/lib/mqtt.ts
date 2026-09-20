/**
 * Browser MQTT client for SHARP live runtime telemetry.
 *
 * The browser displays home/<house>/runtime, which is produced by the
 * Raspberry Pi runtime bridge after merging model-input context with actual
 * actuator ACK/readback state. The raw home/<house>/state topic remains the
 * model/control input and is intentionally not rendered as hardware truth.
 */

import mqtt, { MqttClient } from 'mqtt';
import { Feed, HomeState, Intent, WeatherData } from './contracts';

const HOUSE = process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';
const STALE_AFTER_SECONDS = 20;

const RUNTIME_TOPIC = `home/${HOUSE}/runtime`;
const INTENT_TOPIC = `home/${HOUSE}/intent`;
const ACK_TOPIC = `home/${HOUSE}/actuator/+/ack`;
const PI_HEALTH_TOPIC = `home/${HOUSE}/health/pi`;
const RUNTIME_HEALTH_TOPIC = `home/${HOUSE}/health/runtime`;

function isHomeState(value: unknown): value is HomeState {
  if (!value || typeof value !== 'object') return false;

  const state = value as Partial<HomeState>;

  return (
    typeof state.house_id === 'string' &&
    typeof state.timestamp_ist === 'string' &&
    typeof state.aggregate_power_kw === 'number' &&
    Number.isFinite(state.aggregate_power_kw) &&
    typeof state.sanctioned_load_kw === 'number' &&
    Number.isFinite(state.sanctioned_load_kw) &&
    typeof state.grid_peak_severity === 'number' &&
    Number.isFinite(state.grid_peak_severity) &&
    Array.isArray(state.appliances)
  );
}

export interface PiAck {
  schema_version: string;
  command_id: string;
  appliance_id: string;
  accepted: boolean;
  applied_level: 0 | 1 | 2;
  rejected_reason: string | null;
  gpio_state: 0 | 1;
  measured_w: number | null;
  verification:
    | 'MATCH'
    | 'MISMATCH_STILL_DRAWING'
    | 'MISMATCH_NOT_DRAWING'
    | 'MISMATCH_WRONG_LEVEL'
    | 'NO_METER';
  acked_at: string;
  latency_ms: number;
}

export interface RuntimeHealth {
  source: string;
  status: 'online' | 'offline' | string;
  house_id?: string;
  timestamp_ist?: string;
  input_state_available?: boolean;
  pi_status?: string;
  gpio_enabled?: boolean;
  hardware_confirmed_devices?: number;
  wired_devices?: number;
  measured_power_available?: boolean;
}

export interface FeedHandlers {
  onFeed: (feed: Feed) => void;
  onAck?: (ack: PiAck) => void;
  onPiHealth?: (health: RuntimeHealth) => void;
  onRuntimeHealth?: (health: RuntimeHealth) => void;
}

export function connectFeed({
  onFeed,
  onAck,
  onPiHealth,
  onRuntimeHealth,
}: FeedHandlers): () => void {
  let lastRuntimeMessage = 0;
  let client: MqttClient | null = null;

  const url = process.env.NEXT_PUBLIC_MQTT_URL;

  const emit = (
    status: Feed['status'],
    state: HomeState | null = null,
    intent: Intent | null = null,
  ) => {
    const age = lastRuntimeMessage
      ? (Date.now() - lastRuntimeMessage) / 1000
      : 0;

    const effective: Feed['status'] =
      status === 'live' &&
      lastRuntimeMessage > 0 &&
      age > STALE_AFTER_SECONDS
        ? 'stale'
        : status;

    onFeed({
      status: effective,
      dataAgeSeconds: age,
      state,
      intent,
    });
  };

  if (!url) {
    console.error('NEXT_PUBLIC_MQTT_URL is not configured');
    emit('offline');
    return () => undefined;
  }

  client = mqtt.connect(url, {
    username: process.env.NEXT_PUBLIC_MQTT_USER,
    password: process.env.NEXT_PUBLIC_MQTT_PASS,
    reconnectPeriod: 2000,
    connectTimeout: 10_000,
    clean: true,
    clientId: `sharp-dash-${Math.random().toString(16).slice(2, 10)}`,
  });

  client.on('connect', () => {
    const topics = [
      RUNTIME_TOPIC,
      INTENT_TOPIC,
      ACK_TOPIC,
      PI_HEALTH_TOPIC,
      RUNTIME_HEALTH_TOPIC,
    ];

    client?.subscribe(topics, { qos: 1 }, (error) => {
      if (error) {
        console.error('MQTT subscribe error:', error);
        emit('offline');
        return;
      }

      emit('live');
    });
  });

  client.on('message', (topic, payload) => {
    try {
      const parsed = JSON.parse(payload.toString());

      // IMPORTANT: health/runtime also ends with "/runtime".
      // Match exact topics so a runtime-health payload can never be
      // misinterpreted as a HomeState.
      if (topic === RUNTIME_HEALTH_TOPIC) {
        onRuntimeHealth?.(parsed as RuntimeHealth);
        return;
      }

      if (topic === PI_HEALTH_TOPIC) {
        onPiHealth?.(parsed as RuntimeHealth);
        return;
      }

      if (topic === RUNTIME_TOPIC) {
        if (!isHomeState(parsed)) {
          console.error('Ignoring invalid runtime HomeState payload:', parsed);
          return;
        }

        lastRuntimeMessage = Date.now();
        emit('live', parsed, null);
        return;
      }

      if (topic === INTENT_TOPIC) {
        emit('live', null, parsed as Intent);
        return;
      }

      if (topic.includes('/actuator/') && topic.endsWith('/ack')) {
        onAck?.(parsed as PiAck);
        emit('live');
      }
    } catch (error) {
      console.error('Invalid MQTT JSON:', topic, error);
    }
  });

  client.on('reconnect', () => emit('connecting'));
  client.on('offline', () => emit('offline'));
  client.on('error', (error) => {
    console.error('MQTT error:', error);
    emit('offline');
  });

  const tick = setInterval(() => {
    emit(client?.connected ? 'live' : 'offline');
  }, 1000);

  return () => {
    clearInterval(tick);
    client?.end(true);
  };
}

/**
 * Publish real weather obtained by the dashboard weather adapter to the Pi.
 * This is not a simulated fallback: callers should only pass a fetched live
 * WeatherData object unless the UI explicitly labels a scenario as simulated.
 */
export function publishWeatherStream(weather: WeatherData): boolean {
  const url = process.env.NEXT_PUBLIC_MQTT_URL;
  if (!url) return false;

  try {
    const client = mqtt.connect(url, {
      username: process.env.NEXT_PUBLIC_MQTT_USER,
      password: process.env.NEXT_PUBLIC_MQTT_PASS,
      reconnectPeriod: 0,
      connectTimeout: 5000,
    });

    client.on('connect', () => {
      const topic = `home/${HOUSE}/weather`;
      const payload = JSON.stringify({
        source: 'sharp_dashboard_weather_gateway',
        timestamp: new Date().toISOString(),
        weather,
      });

      client.publish(topic, payload, { qos: 0 }, (error) => {
        if (error) {
          console.error('Failed to publish weather stream:', error);
        }
        client.end();
      });
    });

    client.on('error', (error) => {
      console.error('MQTT weather client error:', error);
      client.end();
    });

    return true;
  } catch (error) {
    console.error('Exception publishing weather:', error);
    return false;
  }
}
