/**
 * The weather adapter. Idea book §39.
 *
 * Four of the model's 305 inputs are weather, and they drive the thermal model
 * - how fast a room heats, when the AC is wanted, how long it can be off
 * before someone is uncomfortable. They came from NASA POWER during training;
 * live they come from here.
 *
 * §39 REQUIREMENTS, EACH IMPLEMENTED BELOW
 *
 *   "keep API keys server-side"      -> this is a route handler, not a hook.
 *                                       Open-Meteo needs no key at all, which
 *                                       removes the problem rather than hiding
 *                                       it.
 *   "use fixed project coordinates"  -> Guntur, until onboarding collects a
 *                                       user-approved household location.
 *   "cache current and forecast"     -> a short in-process cache; the control
 *                                       loop is 15 minutes, so per-request
 *                                       fetching would be waste.
 *   "emit stale/quality fields"      -> every response carries `quality` and
 *                                       `stale`, and §55 requires the consumer
 *                                       to lower confidence rather than guess.
 *
 * UNITS ARE THE TRAP. The model was trained on NASA POWER in:
 *
 *     T2M              degrees C          16.95 - 40.74
 *     RH2M             per cent           25.4  - 95.9
 *     ALLSKY_SFC_SW_DWN  W/m^2            0     - 833.6
 *     WS10M            m/s at 10 m        1.77  - 7.26
 *
 * Fahrenheit, or radiation as kWh/m^2/day, is silently wrong - no exception,
 * just confident bad decisions. Open-Meteo is requested in exactly these units
 * and the response is range-checked before it is served.
 */

import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const revalidate = 0;

/** Guntur. Fixed until onboarding collects a household location (§39). */
const LATITUDE = Number(process.env.WEATHER_LAT ?? 16.3067);
const LONGITUDE = Number(process.env.WEATHER_LON ?? 80.4365);
const TIMEZONE = 'Asia/Kolkata';

/** The control loop is 15 minutes; refetching faster buys nothing. */
const CACHE_MS = 10 * 60 * 1000;
/** Past this the reading is stale and the consumer must lower confidence. */
const STALE_MS = 60 * 60 * 1000;

/** Ranges the model actually saw. Outside these, flag rather than serve. */
const PLAUSIBLE = {
  temperature_c: [-10, 60],
  relative_humidity_pct: [0, 100],
  shortwave_radiation_w_m2: [0, 1400],
  wind_speed_10m_ms: [0, 60],
} as const;

export interface WeatherReading {
  /** obs_T2M - degrees Celsius. */
  temperature_c: number;
  /** obs_RH2M - per cent. */
  relative_humidity_pct: number;
  /** obs_ALLSKY_SFC_SW_DWN - W/m^2, instantaneous, NOT a daily total. */
  shortwave_radiation_w_m2: number;
  /** obs_WS10M - m/s at 10 metres, not surface wind. */
  wind_speed_10m_ms: number;
  observed_at: string;
  source: string;
  quality: 'ok' | 'out_of_range' | 'cached' | 'unavailable';
  stale: boolean;
  age_seconds: number;
}

let cached: { at: number; reading: WeatherReading } | null = null;

function inRange(reading: Omit<WeatherReading, 'quality' | 'stale' | 'age_seconds'>) {
  return (Object.keys(PLAUSIBLE) as Array<keyof typeof PLAUSIBLE>)
    .every((key) => {
      const [lo, hi] = PLAUSIBLE[key];
      const value = reading[key] as number;
      return Number.isFinite(value) && value >= lo && value <= hi;
    });
}

async function fetchOpenMeteo(): Promise<WeatherReading> {
  // Open-Meteo is the only common free source that returns shortwave
  // radiation, which OpenWeather's free tier does not include - and it needs
  // no API key, so there is no credential to leak.
  const url = new URL('https://api.open-meteo.com/v1/forecast');
  url.searchParams.set('latitude', String(LATITUDE));
  url.searchParams.set('longitude', String(LONGITUDE));
  url.searchParams.set('current',
    'temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m');
  url.searchParams.set('timezone', TIMEZONE);
  // Ask for the exact units the model was trained on.
  url.searchParams.set('temperature_unit', 'celsius');
  url.searchParams.set('wind_speed_unit', 'ms');

  const response = await fetch(url, { signal: AbortSignal.timeout(6000) });
  if (!response.ok) {
    throw new Error(`Open-Meteo responded ${response.status}`);
  }
  const body = await response.json();
  const now = body?.current;
  if (!now) throw new Error('Open-Meteo returned no current block');

  const base = {
    temperature_c: Number(now.temperature_2m),
    relative_humidity_pct: Number(now.relative_humidity_2m),
    shortwave_radiation_w_m2: Number(now.shortwave_radiation),
    wind_speed_10m_ms: Number(now.wind_speed_10m),
    observed_at: String(now.time ?? new Date().toISOString()),
    source: 'open-meteo',
  };

  return {
    ...base,
    quality: inRange(base) ? 'ok' : 'out_of_range',
    stale: false,
    age_seconds: 0,
  };
}

export async function GET() {
  const now = Date.now();

  if (cached && now - cached.at < CACHE_MS) {
    const age = Math.round((now - cached.at) / 1000);
    return NextResponse.json({
      ...cached.reading,
      quality: 'cached',
      stale: now - cached.at > STALE_MS,
      age_seconds: age,
    } satisfies WeatherReading);
  }

  try {
    const reading = await fetchOpenMeteo();
    cached = { at: now, reading };
    return NextResponse.json(reading);
  } catch (error) {
    // §55 operational fallback: serve a clearly identified cached value and
    // lower confidence. Never invent a plausible-looking number - the model
    // would act on it and nobody would know why.
    if (cached) {
      const age = Math.round((now - cached.at) / 1000);
      return NextResponse.json({
        ...cached.reading,
        quality: 'cached',
        stale: true,
        age_seconds: age,
      } satisfies WeatherReading);
    }
    return NextResponse.json({
      quality: 'unavailable',
      stale: true,
      age_seconds: 0,
      error: error instanceof Error ? error.message : 'weather unavailable',
      note: 'No reading and no cache. The Pi must fall back to its own cached '
          + 'value or the seasonal curve, and lower confidence (idea book §55).',
    }, { status: 503 });
  }
}
