import { NextRequest, NextResponse } from 'next/server';
import mqtt from 'mqtt';

export const runtime = 'nodejs';
export const maxDuration = 10;

const PUBLISH_TIMEOUT_MS = 6000;

interface GridEventBody {
  action?: 'declare' | 'cancel';
  severity?: number;
  duration_minutes?: number;
}

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
      clientId: `sharp-grid-api-${Math.random().toString(16).slice(2, 10)}`,
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
  let body: GridEventBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Body must be JSON' }, { status: 400 });
  }

  if (body.action !== 'declare' && body.action !== 'cancel') {
    return NextResponse.json(
      { error: 'action must be declare or cancel' },
      { status: 400 },
    );
  }

  const severity =
    body.action === 'cancel' ? 0 : Number(body.severity);

  if (!Number.isFinite(severity) || severity < 0 || severity > 1) {
    return NextResponse.json(
      { error: 'severity must be between 0 and 1' },
      { status: 400 },
    );
  }

  const durationMinutes =
    body.action === 'cancel'
      ? 0
      : Math.max(1, Math.min(240, Number(body.duration_minutes ?? 60)));

  const houseId = process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';
  const url = process.env.MQTT_URL;
  const username = process.env.MQTT_PUBLISH_USER;
  const password = process.env.MQTT_PUBLISH_PASS;

  if (!url) {
    return NextResponse.json(
      { published: false, error: 'MQTT_URL is not configured' },
      { status: 503 },
    );
  }

  const now = new Date();
  const event = {
    schema_version: 'sharp_grid_event_v1',
    event_id: crypto.randomUUID(),
    action: body.action,
    house_id: houseId,
    severity,
    duration_minutes: durationMinutes,
    declared_at: now.toISOString(),
    expires_at:
      body.action === 'declare'
        ? new Date(now.getTime() + durationMinutes * 60_000).toISOString()
        : now.toISOString(),
    source: 'dashboard_grid_controller',
  };

  try {
    await publish(
      url,
      username,
      password,
      `home/${houseId}/grid/event`,
      event,
    );
  } catch (error) {
    return NextResponse.json(
      {
        published: false,
        event,
        error: error instanceof Error ? error.message : 'publish failed',
      },
      { status: 502 },
    );
  }

  return NextResponse.json({
    published: true,
    event,
    note: 'Event reached HiveMQ. Runtime/model state changes only after the edge path processes it.',
  });
}
