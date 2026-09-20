/**
 * Server-side live weather adapter for SHARP.
 *
 * Open-Meteo supplies the four weather variables used by the RL state:
 * temperature, relative humidity, shortwave radiation, and 10 m wind speed.
 *
 * A successful GET also publishes the converted WeatherData payload to
 * home/<house>/weather using the server-side MQTT publish credential. This
 * keeps write credentials out of the browser and lets runtime_bridge.py fold
 * the reading into home/<house>/runtime.
 */

import { NextResponse } from 'next/server';
import mqtt from 'mqtt';

export const runtime = 'nodejs';
export const revalidate = 0;
export const maxDuration = 15;

const LATITUDE = Number(process.env.WEATHER_LAT ?? 16.3067);
const LONGITUDE = Number(process.env.WEATHER_LON ?? 80.4365);
const TIMEZONE = 'Asia/Kolkata';

const HOUSE_ID = process.env.NEXT_PUBLIC_HOUSE_ID ?? 'demo';
const MQTT_URL = process.env.MQTT_URL;
const MQTT_USER = process.env.MQTT_PUBLISH_USER;
const MQTT_PASS = process.env.MQTT_PUBLISH_PASS;

const CACHE_MS = 10 * 60 * 1000;
const STALE_MS = 60 * 60 * 1000;
const MQTT_TIMEOUT_MS = 4000;

const PLAUSIBLE = {
  temperature_c: [-10, 60],
  relative_humidity_pct: [0, 100],
  shortwave_radiation_w_m2: [0, 1400],
  wind_speed_10m_ms: [0, 60],
} as const;

export interface WeatherReading {
  temperature_c: number;
  relative_humidity_pct: number;
  shortwave_radiation_w_m2: number;
  wind_speed_10m_ms: number;
  observed_at: string;
  source: string;
  quality: 'ok' | 'out_of_range' | 'cached' | 'unavailable';
  stale: boolean;
  age_seconds: number;
}

let cached: { at: number; reading: WeatherReading } | null = null;

function inRange(
  reading: Omit<WeatherReading, 'quality' | 'stale' | 'age_seconds'>,
) {
  return (Object.keys(PLAUSIBLE) as Array<keyof typeof PLAUSIBLE>).every(
    (key) => {
      const [lo, hi] = PLAUSIBLE[key];
      const value = reading[key] as number;
      return Number.isFinite(value) && value >= lo && value <= hi;
    },
  );
}

function calculateHeatIndex(tempC: number, humidityPct: number): number {
  if (tempC < 27) return tempC;

  const t = (tempC * 9) / 5 + 32;
  const r = humidityPct;

  const hi =
    -42.379 +
    2.04901523 * t +
    10.14333127 * r -
    0.22475541 * t * r -
    0.00683783 * t * t -
    0.05481717 * r * r +
    0.00122874 * t * t * r +
    0.00085282 * t * r * r -
    0.00000199 * t * t * r * r;

  return Number((((hi - 32) * 5) / 9).toFixed(1));
}

function toDashboardWeather(reading: WeatherReading) {
  const temp = reading.temperature_c;
  const humidity = reading.relative_humidity_pct;

  return {
    outdoor_temperature_c: temp,
    relative_humidity_pct: humidity,
    solar_irradiance_wm2: reading.shortwave_radiation_w_m2,
    heat_index_c: calculateHeatIndex(temp, humidity),
    wind_speed_kmh: Number((reading.wind_speed_10m_ms * 3.6).toFixed(1)),
    weather_condition:
      reading.quality === 'cached'
        ? 'Cached live weather'
        : reading.quality === 'out_of_range'
          ? 'Live weather — quality warning'
          : 'Live weather',
    location: 'Guntur, Andhra Pradesh',
    last_updated: reading.observed_at,
    is_extreme_heat: temp >= 40,
  };
}

async function fetchOpenMeteo(): Promise<WeatherReading> {
  const url = new URL('https://api.open-meteo.com/v1/forecast');

  url.searchParams.set('latitude', String(LATITUDE));
  url.searchParams.set('longitude', String(LONGITUDE));
  url.searchParams.set(
    'current',
    'temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m',
  );
  url.searchParams.set('timezone', TIMEZONE);
  url.searchParams.set('temperature_unit', 'celsius');
  url.searchParams.set('wind_speed_unit', 'ms');

  const response = await fetch(url, {
    cache: 'no-store',
    signal: AbortSignal.timeout(6000),
  });

  if (!response.ok) {
    throw new Error(`Open-Meteo responded ${response.status}`);
  }

  const body = await response.json();
  const current = body?.current;

  if (!current) {
    throw new Error('Open-Meteo returned no current block');
  }

  const base = {
    temperature_c: Number(current.temperature_2m),
    relative_humidity_pct: Number(current.relative_humidity_2m),
    shortwave_radiation_w_m2: Number(current.shortwave_radiation),
    wind_speed_10m_ms: Number(current.wind_speed_10m),
    observed_at: String(current.time ?? new Date().toISOString()),
    source: 'open-meteo',
  };

  return {
    ...base,
    quality: inRange(base) ? 'ok' : 'out_of_range',
    stale: false,
    age_seconds: 0,
  };
}

function publishMqtt(topic: string, payload: unknown): Promise<void> {
  if (!MQTT_URL) {
    return Promise.reject(new Error('MQTT_URL is not configured'));
  }

  return new Promise((resolve, reject) => {
    const client = mqtt.connect(MQTT_URL, {
      username: MQTT_USER,
      password: MQTT_PASS,
      reconnectPeriod: 0,
      connectTimeout: MQTT_TIMEOUT_MS,
      clean: true,
      clientId: `sharp-weather-api-${Math.random().toString(16).slice(2, 10)}`,
    });

    let finished = false;

    const finish = (error?: Error) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      client.end(true, () => (error ? reject(error) : resolve()));
    };

    const timer = setTimeout(
      () => finish(new Error('MQTT weather publish timed out')),
      MQTT_TIMEOUT_MS,
    );

    client.on('error', (error) => finish(error as Error));

    client.on('connect', () => {
      client.publish(topic, JSON.stringify(payload), { qos: 1 }, (error) => {
        finish(error ?? undefined);
      });
    });
  });
}

async function publishWeatherToRuntime(reading: WeatherReading): Promise<boolean> {
  if (!MQTT_URL) return false;

  try {
    await publishMqtt(`home/${HOUSE_ID}/weather`, {
      source: 'sharp_server_weather_gateway',
      timestamp: new Date().toISOString(),
      weather: toDashboardWeather(reading),
    });
    return true;
  } catch (error) {
    console.error('Weather MQTT publish failed:', error);
    return false;
  }
}

async function respondWithReading(reading: WeatherReading) {
  const mqttPublished = await publishWeatherToRuntime(reading);

  return NextResponse.json({
    ...reading,
    mqtt_published: mqttPublished,
  });
}

export async function GET() {
  const now = Date.now();

  if (cached && now - cached.at < CACHE_MS) {
    const age = Math.round((now - cached.at) / 1000);

    const reading: WeatherReading = {
      ...cached.reading,
      quality: 'cached',
      stale: now - cached.at > STALE_MS,
      age_seconds: age,
    };

    return respondWithReading(reading);
  }

  try {
    const reading = await fetchOpenMeteo();
    cached = { at: now, reading };
    return respondWithReading(reading);
  } catch (error) {
    if (cached) {
      const age = Math.round((now - cached.at) / 1000);

      const reading: WeatherReading = {
        ...cached.reading,
        quality: 'cached',
        stale: true,
        age_seconds: age,
      };

      return respondWithReading(reading);
    }

    return NextResponse.json(
      {
        quality: 'unavailable',
        stale: true,
        age_seconds: 0,
        error:
          error instanceof Error ? error.message : 'weather unavailable',
        note:
          'No weather reading and no cache are available. No fabricated fallback was used.',
      },
      { status: 503 },
    );
  }
}
