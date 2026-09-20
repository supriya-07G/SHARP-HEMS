import { WeatherData } from './contracts';

export function calculateHeatIndex(tempC: number, humidityPct: number): number {
  if (tempC < 27) return tempC;
  const T = (tempC * 9) / 5 + 32;
  const R = humidityPct;
  const c1 = -42.379, c2 = 2.04901523, c3 = 10.14333127, c4 = -0.22475541;
  const c5 = -0.00683783, c6 = -0.05481717, c7 = 0.00122874, c8 = 0.00085282, c9 = -0.00000199;
  const hi = c1 + c2*T + c3*R + c4*T*R + c5*T*T + c6*R*R + c7*T*T*R + c8*T*R*R + c9*T*T*R*R;
  return Number((((hi - 32) * 5) / 9).toFixed(1));
}

/**
 * Fetch current weather from the server-side weather adapter.
 * No fabricated fallback is returned: callers must render unavailable/stale
 * explicitly when the source cannot provide a reading.
 */
export async function fetchLiveGunturWeather(): Promise<WeatherData> {
  const res = await fetch('/api/weather', {
    cache: 'no-store',
    signal: AbortSignal.timeout(7000),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error ?? `weather unavailable (${res.status})`);
  }

  const current = await res.json();

  if (
    typeof current.temperature_c !== 'number' ||
    typeof current.relative_humidity_pct !== 'number' ||
    typeof current.shortwave_radiation_w_m2 !== 'number' ||
    typeof current.wind_speed_10m_ms !== 'number'
  ) {
    throw new Error('weather adapter returned incomplete data');
  }

  const temp = current.temperature_c;
  const humidity = current.relative_humidity_pct;

  return {
    outdoor_temperature_c: temp,
    relative_humidity_pct: humidity,
    solar_irradiance_wm2: current.shortwave_radiation_w_m2,
    heat_index_c: calculateHeatIndex(temp, humidity),
    wind_speed_kmh: Number((current.wind_speed_10m_ms * 3.6).toFixed(1)),
    weather_condition:
      current.quality === 'cached'
        ? 'Cached live weather'
        : current.quality === 'out_of_range'
          ? 'Live weather — quality warning'
          : 'Live weather',
    location: 'Guntur, Andhra Pradesh',
    last_updated: current.observed_at,
    is_extreme_heat: temp >= 40,
  };
}
