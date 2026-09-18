import { WeatherData } from './contracts';

/**
 * Default Guntur, Andhra Pradesh Weather Baseline
 * Matches SHARP integration dataset (NASA POWER city-cell reanalysis for Guntur AP).
 */
export const DEFAULT_GUNTUR_WEATHER: WeatherData = {
  outdoor_temperature_c: 35.2,
  relative_humidity_pct: 62.0,
  solar_irradiance_wm2: 850.0,
  heat_index_c: 41.8,
  wind_speed_kmh: 14.5,
  weather_condition: 'Hot & Humid (Peak Solar)',
  location: 'Guntur Urban, Andhra Pradesh (APCPDCL)',
  last_updated: '14:05 IST',
  is_extreme_heat: false,
};

/**
 * Weather simulation presets for testing RL policy adaptation under extreme forcing
 */
export const WEATHER_PRESETS: Record<string, { label: string; weather: WeatherData }> = {
  normal: {
    label: '☀️ Normal Midday (35°C)',
    weather: DEFAULT_GUNTUR_WEATHER,
  },
  heatwave: {
    label: '🔥 Summer Heatwave (42°C)',
    weather: {
      outdoor_temperature_c: 42.4,
      relative_humidity_pct: 45.0,
      solar_irradiance_wm2: 1050.0,
      heat_index_c: 48.6,
      wind_speed_kmh: 8.2,
      weather_condition: 'Extreme Heatwave Warning',
      location: 'Guntur Urban, Andhra Pradesh (APCPDCL)',
      last_updated: '14:05 IST',
      is_extreme_heat: true,
    },
  },
  monsoon: {
    label: '🌧️ Heavy Monsoon (29°C)',
    weather: {
      outdoor_temperature_c: 29.1,
      relative_humidity_pct: 88.0,
      solar_irradiance_wm2: 180.0,
      heat_index_c: 34.2,
      wind_speed_kmh: 24.0,
      weather_condition: 'Overcast & Rain',
      location: 'Guntur Urban, Andhra Pradesh (APCPDCL)',
      last_updated: '14:05 IST',
      is_extreme_heat: false,
    },
  },
  cool_night: {
    label: '🌙 Mild Night (24°C)',
    weather: {
      outdoor_temperature_c: 24.5,
      relative_humidity_pct: 70.0,
      solar_irradiance_wm2: 0.0,
      heat_index_c: 25.1,
      wind_speed_kmh: 6.0,
      weather_condition: 'Clear Sky (Night)',
      location: 'Guntur Urban, Andhra Pradesh (APCPDCL)',
      last_updated: '22:15 IST',
      is_extreme_heat: false,
    },
  },
};

/**
 * Calculate approximate Heat Index (°C) given outdoor temperature and humidity
 */
export function calculateHeatIndex(tempC: number, humidityPct: number): number {
  if (tempC < 27) return tempC;
  const T = (tempC * 9) / 5 + 32; // Convert to Fahrenheit
  const R = humidityPct;
  const c1 = -42.379, c2 = 2.04901523, c3 = 10.14333127, c4 = -0.22475541;
  const c5 = -0.00683783, c6 = -0.05481717, c7 = 0.00122874, c8 = 0.00085282, c9 = -0.00000199;
  
  const hi = c1 + c2*T + c3*R + c4*T*R + c5*T*T + c6*R*R + c7*T*T*R + c8*T*R*R + c9*T*T*R*R;
  const hiC = ((hi - 32) * 5) / 9;
  return parseFloat(hiC.toFixed(1));
}

/**
 * Fetch live weather data for Guntur, Andhra Pradesh (Open-Meteo free API)
 * Falls back cleanly to DEFAULT_GUNTUR_WEATHER on network/CORS error.
 */
export async function fetchLiveGunturWeather(): Promise<WeatherData> {
  try {
    const res = await fetch(
      'https://api.open-meteo.com/v1/forecast?latitude=16.3067&longitude=80.4365&current=temperature_2m,relative_humidity_2m,surface_solar_radiation,wind_speed_10m',
      { signal: AbortSignal.timeout(4000) }
    );
    
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    const current = data.current;
    
    if (!current) throw new Error('No current weather fields returned');
    
    const temp = current.temperature_2m ?? 35.2;
    const humidity = current.relative_humidity_2m ?? 62.0;
    const solar = current.surface_solar_radiation ?? 850.0;
    const wind = current.wind_speed_10m ?? 14.5;
    const heatIndex = calculateHeatIndex(temp, humidity);
    const isExtreme = temp >= 40.0;

    let condition = 'Partly Cloudy';
    if (solar > 750 && temp > 35) condition = 'Hot & Sunny';
    else if (isExtreme) condition = 'Extreme Heatwave Warning';
    else if (solar < 200) condition = 'Cloudy / Overcast';

    return {
      outdoor_temperature_c: parseFloat(temp.toFixed(1)),
      relative_humidity_pct: parseFloat(humidity.toFixed(1)),
      solar_irradiance_wm2: parseFloat(solar.toFixed(1)),
      heat_index_c: heatIndex,
      wind_speed_kmh: parseFloat(wind.toFixed(1)),
      weather_condition: condition,
      location: 'Guntur Urban, Andhra Pradesh (APCPDCL)',
      last_updated: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
      is_extreme_heat: isExtreme,
    };
  } catch (err) {
    console.warn('⚠️ Weather API unavailable, using Guntur baseline dataset:', err);
    return {
      ...DEFAULT_GUNTUR_WEATHER,
      last_updated: `${new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} (Offline Sync)`,
    };
  }
}
