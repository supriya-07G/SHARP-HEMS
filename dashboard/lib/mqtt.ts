/**
 * Browser MQTT client. Runs in the BROWSER, never on Vercel's server.
 *
 * Vercel functions are request-scoped: they wake, answer, freeze. A frozen
 * function drops a long-lived subscription, and you get intermittent missing
 * telemetry that is painful to diagnose. So the client lives here, in the page.
 *
 * MQTT over WebSockets Secure is used so the browser can connect to HiveMQ.
 */

import mqtt, { MqttClient } from 'mqtt';
import { Feed, HomeState, Intent, WeatherData } from './contracts';

const HOUSE = process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';

/** Past this point, received telemetry is considered stale. */
const STALE_AFTER_SECONDS = 30 * 60;

/**
 * Pi ACK payload — published by pi_agent.py on
 * home/<house>/actuator/<appliance_id>/ack after every dashboard override.
 * The dashboard must NOT update appliance state until this arrives.
 */
export interface PiAck {
  schema_version: string;
  command_id: string;
  appliance_id: string;
  accepted: boolean;
  applied_level: 0 | 1 | 2;
  rejected_reason: string | null;
  gpio_state: 0 | 1;
  measured_w: number | null;
  verification: 'MATCH' | 'MISMATCH_STILL_DRAWING' | 'MISMATCH_NOT_DRAWING' | 'MISMATCH_WRONG_LEVEL' | 'NO_METER';
  acked_at: string;
  latency_ms: number;
}

export interface FeedHandlers {
  onFeed: (feed: Feed) => void;
  /**
   * Called when the Raspberry Pi publishes an ACK on
   * home/<house>/actuator/<id>/ack  (QoS 1).
   * The dashboard must NOT mark an appliance as switched until this fires.
   */
  onAck?: (ack: PiAck) => void;
}

export function connectFeed({ onFeed, onAck }: FeedHandlers): () => void {
  let state: HomeState | null = null;
  let intent: Intent | null = null;
  let lastMessage = 0;
  let client: MqttClient | null = null;

  const url = process.env.NEXT_PUBLIC_MQTT_URL;

  // ------------------------------------------------------------
  // MQTT URL CHECK
  // ------------------------------------------------------------

  if (!url) {
    console.error('❌ NEXT_PUBLIC_MQTT_URL is not configured');

    onFeed({
      status: 'offline',
      dataAgeSeconds: 0,
      state: null,
      intent: null,
    });

    return () => undefined;
  }

  console.log('🔌 Connecting to HiveMQ...');

  // ------------------------------------------------------------
  // MQTT CONFIG DIAGNOSTIC
  // ------------------------------------------------------------

  console.log('🔎 MQTT CONFIG:', {
    url,
    user: process.env.NEXT_PUBLIC_MQTT_USER,
    hasPassword: !!process.env.NEXT_PUBLIC_MQTT_PASS,
  });

  // ------------------------------------------------------------
  // FEED EMITTER
  // ------------------------------------------------------------

  const emit = (
    status: Feed['status'],
    freshState: HomeState | null = null,
    freshIntent: Intent | null = null,
  ) => {
    const age = lastMessage
      ? (Date.now() - lastMessage) / 1000
      : 0;

    const effective =
      status === 'live' &&
      lastMessage &&
      age > STALE_AFTER_SECONDS
        ? 'stale'
        : status;

    // IMPORTANT:
    // Only forward state/intent when that exact MQTT topic has just arrived.
    // Re-emitting cached retained state after a Pi ACK would overwrite the
    // hardware-confirmed level that useHomeState just applied.
    onFeed({
      status: effective,
      dataAgeSeconds: age,
      state: freshState,
      intent: freshIntent,
    });
  };

  // ------------------------------------------------------------
  // CONNECT TO HIVEMQ
  // ------------------------------------------------------------

  client = mqtt.connect(url, {
    username: process.env.NEXT_PUBLIC_MQTT_USER,
    password: process.env.NEXT_PUBLIC_MQTT_PASS,

    reconnectPeriod: 2000,
    connectTimeout: 10_000,

    clean: true,

    clientId: `sharp-dash-${Math.random()
      .toString(16)
      .slice(2, 10)}`,
  });

  // ------------------------------------------------------------
  // CONNECT EVENT
  // ------------------------------------------------------------

  client.on('connect', () => {
    console.log('✅ MQTT CONNECTED TO HIVEMQ');

    const topics = [
      `home/${HOUSE}/state`,
      `home/${HOUSE}/intent`,
      // Pi ACK topic — wildcard covers all appliance IDs.
      // QoS 1 so we never miss an ACK on a flaky connection.
      `home/${HOUSE}/actuator/+/ack`,
    ];

    console.log('📡 Subscribing to:', topics);

    client?.subscribe(
      topics,
      { qos: 1 },
      (error) => {
        if (error) {
          console.error(
            '❌ MQTT SUBSCRIBE ERROR:',
            error
          );
          return;
        }

        console.log(
          '✅ MQTT SUBSCRIBED:',
          topics
        );

        emit('live');
      }
    );
  });

  // ------------------------------------------------------------
  // MESSAGE EVENT
  // ------------------------------------------------------------

  client.on('message', (topic, payload) => {
    console.log(
      '📨 MQTT MESSAGE:',
      topic,
      payload.toString()
    );

    try {
      const parsed = JSON.parse(
        payload.toString()
      );

      if (topic.endsWith('/state')) {
        state = parsed as HomeState;
        lastMessage = Date.now();

        console.log(
          '🏠 HomeState received'
        );

        emit('live', state, null);
      } else if (topic.endsWith('/intent')) {
        intent = parsed as Intent;
        lastMessage = Date.now();

        console.log(
          '🤖 Intent received'
        );

        emit('live', null, intent);
      } else if (
        topic.includes('/actuator/') &&
        topic.endsWith('/ack')
      ) {
        // Raspberry Pi hardware ACK — the only thing that confirms
        // GPIO changed. Do not replay cached HomeState after this ACK.
        const ack = parsed as PiAck;
        lastMessage = Date.now();

        console.log(
          '✅ Pi ACK received:',
          ack.appliance_id,
          ack.accepted ? 'ACCEPTED' : 'REJECTED',
          `gpio_state=${ack.gpio_state}`
        );

        onAck?.(ack);

        // Status-only update. state/intent stay null so the ACK-confirmed
        // appliance level in useHomeState is not overwritten.
        emit('live');
      }
    } catch (error) {
      console.error(
        '❌ Invalid MQTT JSON:',
        error
      );
    }
  });

  // ------------------------------------------------------------
  // RECONNECT
  // ------------------------------------------------------------

  client.on('reconnect', () => {
    console.log('🔄 MQTT reconnecting...');
    emit('connecting');
  });

  // ------------------------------------------------------------
  // OFFLINE
  // ------------------------------------------------------------

  client.on('offline', () => {
    console.log('⚠️ MQTT offline');
    emit('offline');
  });

  // ------------------------------------------------------------
  // ERROR
  // ------------------------------------------------------------

  client.on('error', (error) => {
    console.error(
      '❌ MQTT ERROR:',
      error
    );

    emit('offline');
  });

  // ------------------------------------------------------------
  // DATA AGE TIMER
  // ------------------------------------------------------------

  const tick = setInterval(() => {
    emit(
      client?.connected
        ? 'live'
        : 'offline'
    );
  }, 1000);

  // ------------------------------------------------------------
  // CLEANUP
  // ------------------------------------------------------------

  return () => {
    console.log(
      '🔌 Disconnecting MQTT...'
    );

    clearInterval(tick);

    client?.end(true);
  };
}

/**
 * Publish Weather Payload to Raspberry Pi over MQTT (`home/${HOUSE}/weather`)
 */
export function publishWeatherStream(weather: WeatherData): boolean {
  const url = process.env.NEXT_PUBLIC_MQTT_URL;
  if (!url) {
    console.warn('⚠️ MQTT URL not configured. Cannot stream weather payload.');
    return false;
  }

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

      client.publish(topic, payload, { qos: 0 }, (err) => {
        if (err) console.error('❌ Failed to publish weather stream:', err);
        else console.log('📡 Published Weather Payload to Pi:', topic, weather);
        client.end();
      });
    });

    client.on('error', (err) => {
      console.error('❌ MQTT Weather Client Error:', err);
      client.end();
    });

    return true;
  } catch (err) {
    console.error('❌ Exception publishing weather:', err);
    return false;
  }
}