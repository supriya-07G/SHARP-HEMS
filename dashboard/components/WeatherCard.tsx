'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { WeatherData } from '../lib/contracts';
import { fetchLiveGunturWeather } from '../lib/weather';

interface WeatherCardProps {
  weather?: WeatherData;
  onWeatherUpdate?: (newWeather: WeatherData) => void;
  className?: string;
}

export const WeatherCard: React.FC<WeatherCardProps> = ({
  weather,
  onWeatherUpdate,
  className = '',
}) => {
  const [displayWeather, setDisplayWeather] = useState<WeatherData | undefined>(
    weather,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (weather) {
      setDisplayWeather(weather);
    }
  }, [weather]);

  const loadLiveWeather = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const live = await fetchLiveGunturWeather();

      // Show the successful server response immediately. The same API request
      // also publishes the reading to HiveMQ server-side; runtime_bridge.py
      // will later echo it back inside home/<house>/runtime.
      setDisplayWeather(live);
      onWeatherUpdate?.(live);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Weather unavailable');
    } finally {
      setIsLoading(false);
    }
  }, [onWeatherUpdate]);

  // A live-weather card should populate itself on first render rather than
  // requiring a manual click. Existing runtime weather remains authoritative
  // when it is already present.
  useEffect(() => {
    if (!weather) {
      void loadLiveWeather();
    }
  }, [weather, loadLiveWeather]);

  return (
    <div
      className={`rounded-2xl border border-[#e5eaf2] bg-white p-5 shadow-sm ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Live weather</p>
          <h3 className="font-semibold text-[#17365D]">
            Guntur weather gateway
          </h3>
        </div>

        <button
          type="button"
          onClick={() => void loadLiveWeather()}
          disabled={isLoading}
          className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800 disabled:opacity-50"
        >
          {isLoading ? 'Refreshing…' : 'Refresh live weather'}
        </button>
      </div>

      {!displayWeather ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-500">
          {isLoading
            ? 'Fetching live Open-Meteo weather…'
            : 'Live weather is currently unavailable.'}
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric
            label="Outdoor"
            value={`${displayWeather.outdoor_temperature_c.toFixed(1)} °C`}
          />
          <Metric
            label="Humidity"
            value={`${displayWeather.relative_humidity_pct.toFixed(0)} %`}
          />
          <Metric
            label="Solar"
            value={`${displayWeather.solar_irradiance_wm2.toFixed(0)} W/m²`}
          />
          <Metric
            label="Wind"
            value={`${displayWeather.wind_speed_kmh.toFixed(1)} km/h`}
          />
        </div>
      )}

      {displayWeather && (
        <p className="mt-3 text-[11px] text-slate-500">
          {displayWeather.weather_condition} · {displayWeather.location} · observed{' '}
          {displayWeather.last_updated}
        </p>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">
          {error}
        </p>
      )}
    </div>
  );
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="text-[11px] font-medium text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-lg font-bold text-[#17365D]">
        {value}
      </div>
    </div>
  );
}
