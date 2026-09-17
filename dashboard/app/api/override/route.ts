/**
 * The browser -> hardware path.
 *
 * WHY THIS RUNS ON THE SERVER AND NOT IN THE PAGE
 *
 * Anything in `NEXT_PUBLIC_*` is visible to everyone who opens the dashboard.
 * A leaked SUBSCRIBE credential lets a stranger read demo telemetry; a leaked
 * PUBLISH credential lets them command your relays. So the browser subscribes
 * with a read-only user, and every write goes through here with a credential
 * that never reaches the client.
 *
 * WHY A SERVERLESS FUNCTION IS FINE FOR THIS
 *
 * The objection to serverless + MQTT is that a frozen function drops a
 * long-lived SUBSCRIPTION. Publishing is the opposite shape: connect, publish,
 * wait for the broker's acknowledgement, disconnect - a few hundred
 * milliseconds, entirely request-scoped. Live state never comes through here;
 * the browser subscribes directly.
 *
 * WHAT THIS DOES NOT DO
 *
 * It does not decide anything. It records intent and hands it to the Pi, whose
 * shield is the authority and may refuse - during a peak the luxury circuit
 * has no power to give, and no amount of asking changes that. Never report
 * success here as though the appliance switched on.
 */

import { NextRequest, NextResponse } from 'next/server';
import mqtt from 'mqtt';

export const runtime = 'nodejs';
export const maxDuration = 10;

const PUBLISH_TIMEOUT_MS = 6000;

interface OverrideBody {
  house_id?: string;
  appliance_id?: string;
  requested_level?: 0 | 1 | 2;
  /** Milliseconds from the notice appearing to the tap. THE preference signal. */
  client_latency_ms?: number;
  reason?: string;
}

function badRequest(message: string) {
  return NextResponse.json({ accepted: false, error: message }, { status: 400 });
}

export async function POST(request: NextRequest) {
  let body: OverrideBody;
  try {
    body = await request.json();
  } catch {
    return badRequest('Body must be JSON');
  }

  const houseId = body.house_id ?? process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';
  const applianceId = body.appliance_id;
  const level = body.requested_level;

  if (!applianceId || !/^[a-z_]+_\d{2}$/.test(applianceId)) {
    return badRequest('appliance_id must look like ceiling_fan_01');
  }
  if (level !== 0 && level !== 1 && level !== 2) {
    return badRequest('requested_level must be 0, 1 or 2');
  }

  const url = process.env.MQTT_URL;
  const username = process.env.MQTT_PUBLISH_USER;
  const password = process.env.MQTT_PUBLISH_PASS;

  const command = {
    override_id: crypto.randomUUID(),
    house_id: houseId,
    appliance_id: applianceId,
    requested_level: level,
    client_latency_ms: body.client_latency_ms ?? null,
    reason: body.reason ?? 'resident_override',
    issued_at: new Date().toISOString(),
    // The Pi rejects a stale command rather than acting on it late.
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
    source: 'dashboard',
  };

  // No broker configured: accept and say plainly that nothing was published.
  // Reporting success here would be a lie the demo could not detect.
  if (!url) {
    return NextResponse.json({
      accepted: false,
      published: false,
      command,
      note: 'MQTT_URL is not set. Nothing was published; the request was not '
          + 'delivered to any Pi.',
    }, { status: 503 });
  }

  try {
    await publish(url, username, password,
      `home/${houseId}/override/${applianceId}`, command);
  } catch (error) {
    return NextResponse.json({
      accepted: false,
      published: false,
      command,
      error: error instanceof Error ? error.message : 'publish failed',
    }, { status: 502 });
  }

  return NextResponse.json({
    accepted: true,
    published: true,
    command,
    // Said explicitly: delivery is not the same as the appliance switching on.
    note: 'Delivered to the broker. The Pi shield decides whether it is applied '
        + 'and may refuse with a reason.',
  });
}

function publish(
  url: string, username: string | undefined, password: string | undefined,
  topic: string, payload: unknown,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const client = mqtt.connect(url, {
      username,
      password,
      connectTimeout: PUBLISH_TIMEOUT_MS,
      reconnectPeriod: 0,          // one attempt; this is request-scoped
      clean: true,
      clientId: `sharp-api-${Math.random().toString(16).slice(2, 10)}`,
    });

    const done = (error?: Error) => {
      clearTimeout(timer);
      client.end(true, () => (error ? reject(error) : resolve()));
    };

    const timer = setTimeout(
      () => done(new Error('Broker did not respond in time')),
      PUBLISH_TIMEOUT_MS,
    );

    client.on('error', (error) => done(error as Error));
    client.on('connect', () => {
      // QoS 1: at-least-once. An override that silently vanishes is worse than
      // one delivered twice, which the Pi de-duplicates on override_id.
      client.publish(topic, JSON.stringify(payload), { qos: 1 },
        (error) => done(error ?? undefined));
    });
  });
}
