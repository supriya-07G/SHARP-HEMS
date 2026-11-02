/**
 * Choose the house scenario from the dashboard.
 *
 * Publishes a retained request on home/<house>/scenario/set. The Pi's
 * scenario service (hardware/scenario_service.py) applies it and reports
 * back on home/<house>/scenario/active. Retained, so a Pi that reboots
 * resumes the last scenario chosen here.
 *
 * Like the other write routes, this runs on the server so the publish
 * credential never reaches the browser.
 */

import { NextRequest, NextResponse } from 'next/server';
import mqtt from 'mqtt';
import { DEMO_SCENARIOS, isDemoScenario } from '@/lib/scenarios';

export const runtime = 'nodejs';
export const maxDuration = 10;

const PUBLISH_TIMEOUT_MS = 6000;

function publish(
  url: string,
  username: string | undefined,
  password: string | undefined,
  topic: string,
  payload: unknown,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const client = mqtt.connect(url, {
      username,
      password,
      connectTimeout: PUBLISH_TIMEOUT_MS,
      reconnectPeriod: 0,
      clean: true,
      clientId: `sharp-scenario-api-${Math.random().toString(16).slice(2, 10)}`,
    });

    let finished = false;

    const done = (error?: Error) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      client.end(true, () => (error ? reject(error) : resolve()));
    };

    const timer = setTimeout(
      () => done(new Error('Broker did not respond in time')),
      PUBLISH_TIMEOUT_MS,
    );

    client.on('error', (error) => done(error as Error));
    client.on('connect', () => {
      client.publish(topic, JSON.stringify(payload), { qos: 1, retain: true },
        (error) => done(error ?? undefined));
    });
  });
}

export async function POST(request: NextRequest) {
  let body: { scenario?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Body must be JSON' }, { status: 400 });
  }

  if (!isDemoScenario(body.scenario)) {
    return NextResponse.json(
      { error: `scenario must be one of ${DEMO_SCENARIOS.map((s) => s.id).join(', ')}` },
      { status: 400 },
    );
  }

  const houseId = process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';
  const url = process.env.MQTT_URL;

  if (!url) {
    return NextResponse.json(
      { published: false, error: 'MQTT_URL is not configured' },
      { status: 503 },
    );
  }

  const requestMessage = {
    schema_version: 'sharp_scenario_request_v1',
    house_id: houseId,
    scenario: body.scenario,
    requested_at: new Date().toISOString(),
    source: 'dashboard',
  };

  try {
    await publish(
      url,
      process.env.MQTT_PUBLISH_USER,
      process.env.MQTT_PUBLISH_PASS,
      `home/${houseId}/scenario/set`,
      requestMessage,
    );
  } catch (error) {
    return NextResponse.json(
      {
        published: false,
        request: requestMessage,
        error: error instanceof Error ? error.message : 'publish failed',
      },
      { status: 502 },
    );
  }

  return NextResponse.json({
    published: true,
    request: requestMessage,
    note: 'Request reached HiveMQ. It takes effect when the Pi scenario service applies it.',
  });
}
