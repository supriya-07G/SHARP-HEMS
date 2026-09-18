'use client';

import React, { useState } from 'react';
import { WeatherData } from '../lib/contracts';
import { DEFAULT_GUNTUR_WEATHER, WEATHER_PRESETS, fetchLiveGunturWeather, calculateHeatIndex } from '../lib/weather';
import { publishWeatherStream } from '../lib/mqtt';

interface WeatherCardProps {
  weather?: WeatherData;
  onWeatherUpdate?: (newWeather: WeatherData) => void;
  className?: string;
}

export const WeatherCard: React.FC<WeatherCardProps> = ({
  weather: initialWeather,
  onWeatherUpdate,
  className = '',
}) => {
  const [prevInitial, setPrevInitial] = useState(initialWeather);
  const [currentWeather, setCurrentWeather] = useState<WeatherData>(
    initialWeather ?? DEFAULT_GUNTUR_WEATHER
  );
  if (initialWeather !== prevInitial) {
    setPrevInitial(initialWeather);
    if (initialWeather) {
      setCurrentWeather(initialWeather);
    }
  }
  const [isLoadingLive, setIsLoadingLive] = useState(false);
  const [isBroadcasting, setIsBroadcasting] = useState(false);
  const [broadcastStatus, setBroadcastStatus] = useState<string | null>(null);
  const [activePreset, setActivePreset] = useState<string>('normal');

  const handleFetchLive = async () => {
    setIsLoadingLive(true);
    try {
      const live = await fetchLiveGunturWeather();
      setCurrentWeather(live);
      if (onWeatherUpdate) onWeatherUpdate(live);
      setActivePreset('custom');
      setBroadcastStatus('Synced live Guntur AP weather!');
      setTimeout(() => setBroadcastStatus(null), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingLive(false);
    }
  };

  const handleApplyPreset = (presetKey: string) => {
    const preset = WEATHER_PRESETS[presetKey];
    if (!preset) return;
    setActivePreset(presetKey);
    const updated = {
      ...preset.weather,
      last_updated: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
    };
    setCurrentWeather(updated);
    if (onWeatherUpdate) onWeatherUpdate(updated);
  };

  const handleTempChange = (newTemp: number) => {
    const heatIndex = calculateHeatIndex(newTemp, currentWeather.relative_humidity_pct);
    const updated: WeatherData = {
      ...currentWeather,
      outdoor_temperature_c: newTemp,
      heat_index_c: heatIndex,
      is_extreme_heat: newTemp >= 40.0,
      weather_condition: newTemp >= 40.0 ? 'Extreme Heatwave Warning' : currentWeather.weather_condition,
      last_updated: `${new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} (Simulated)`,
    };
    setActivePreset('custom');
    setCurrentWeather(updated);
    if (onWeatherUpdate) onWeatherUpdate(updated);
  };

  const handleBroadcastToPi = () => {
    setIsBroadcasting(true);
    setBroadcastStatus('Sending MQTT payload to Pi...');
    
    setTimeout(() => {
      const success = publishWeatherStream(currentWeather);
      setIsBroadcasting(false);
      setBroadcastStatus(
        success
          ? '✅ Weather stream dispatched to Raspberry Pi (home/demo/weather)'
          : '⚡ Weather state updated locally & ready for Pi sync'
      );
      setTimeout(() => setBroadcastStatus(null), 4000);
    }, 600);
  };

  return (
    <div className={`bg-gradient-to-br from-sky-900/40 via-sky-950/50 to-slate-900/60 backdrop-blur-md border border-sky-400/30 rounded-2xl p-5 shadow-xl text-sky-100 ${className}`}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-sky-800/40">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-sky-500/20 border border-sky-400/40 flex items-center justify-center text-2xl shadow-inner">
            🌤️
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-lg text-sky-100">Live Weather Gateway & Pi Feed</h3>
              {currentWeather.is_extreme_heat && (
                <span className="px-2 py-0.5 text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full animate-pulse">
                  HEATWAVE ALERT
                </span>
              )}
            </div>
            <p className="text-xs text-sky-300/70">
              {currentWeather.location} • Refreshed: {currentWeather.last_updated}
            </p>
          </div>
        </div>

        {/* Live Weather Fetch Button */}
        <button
          onClick={handleFetchLive}
          disabled={isLoadingLive}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-sky-500/20 hover:bg-sky-500/30 border border-sky-400/30 text-sky-200 rounded-lg transition shadow hover:shadow-sky-500/20 disabled:opacity-50 cursor-pointer"
        >
          <span className={isLoadingLive ? 'animate-spin' : ''}>🔄</span>
          {isLoadingLive ? 'Fetching Open-Meteo...' : 'Fetch Live Weather'}
        </button>
      </div>

      {/* Main Weather Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
        {/* Temperature */}
        <div className="bg-sky-950/60 border border-sky-800/40 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-xs text-sky-300/80 font-medium flex justify-between">
            <span>Outdoor Temp</span>
            <span>🌡️</span>
          </div>
          <div className="text-2xl font-bold text-sky-100 mt-1">
            {currentWeather.outdoor_temperature_c.toFixed(1)}°C
          </div>
          <div className="text-[10px] text-sky-400/70 mt-1">
            Feels like {currentWeather.heat_index_c}°C
          </div>
        </div>

        {/* Relative Humidity */}
        <div className="bg-sky-950/60 border border-sky-800/40 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-xs text-sky-300/80 font-medium flex justify-between">
            <span>Humidity</span>
            <span>💧</span>
          </div>
          <div className="text-2xl font-bold text-sky-100 mt-1">
            {currentWeather.relative_humidity_pct.toFixed(0)}%
          </div>
          <div className="text-[10px] text-sky-400/70 mt-1">
            Dew point ~24°C
          </div>
        </div>

        {/* Solar Irradiance */}
        <div className="bg-sky-950/60 border border-sky-800/40 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-xs text-sky-300/80 font-medium flex justify-between">
            <span>Solar Radiation</span>
            <span>☀️</span>
          </div>
          <div className="text-2xl font-bold text-sky-100 mt-1">
            {currentWeather.solar_irradiance_wm2.toFixed(0)} <span className="text-xs font-normal">W/m²</span>
          </div>
          <div className="text-[10px] text-sky-400/70 mt-1">
            {currentWeather.solar_irradiance_wm2 > 600 ? 'High Solar Generation' : 'Moderate Solar'}
          </div>
        </div>

        {/* Condition */}
        <div className="bg-sky-950/60 border border-sky-800/40 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-xs text-sky-300/80 font-medium flex justify-between">
            <span>Condition</span>
            <span>📍</span>
          </div>
          <div className="text-sm font-semibold text-sky-200 mt-1 line-clamp-1">
            {currentWeather.weather_condition}
          </div>
          <div className="text-[10px] text-sky-400/70 mt-1">
            Wind: {currentWeather.wind_speed_kmh} km/h
          </div>
        </div>
      </div>

      {/* Weather Simulation Slider & Presets */}
      <div className="bg-sky-950/40 border border-sky-800/30 rounded-xl p-3.5 space-y-3 my-4">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-sky-200 flex items-center gap-1.5">
            🎛️ Weather Simulation & Preset Tuning
          </label>
          <span className="text-xs text-sky-400 font-mono">
            {currentWeather.outdoor_temperature_c.toFixed(1)}°C
          </span>
        </div>

        {/* Preset Selector */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {Object.entries(WEATHER_PRESETS).map(([key, item]) => (
            <button
              key={key}
              onClick={() => handleApplyPreset(key)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition text-left cursor-pointer ${
                activePreset === key
                  ? 'bg-sky-500/30 border-sky-400 text-sky-100 shadow-md shadow-sky-500/10 font-semibold'
                  : 'bg-sky-900/30 border-sky-800/50 text-sky-300 hover:bg-sky-800/30'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Temperature Fine-Tuning Slider */}
        <div className="flex items-center gap-3 pt-1">
          <span className="text-xs text-sky-400 font-medium min-w-[36px]">20°C</span>
          <input
            type="range"
            min="20"
            max="45"
            step="0.5"
            value={currentWeather.outdoor_temperature_c}
            onChange={(e) => handleTempChange(parseFloat(e.target.value))}
            className="w-full h-2 bg-sky-950 rounded-lg appearance-none cursor-pointer accent-sky-400 border border-sky-800"
          />
          <span className="text-xs text-amber-300 font-medium min-w-[36px]">45°C</span>
        </div>
      </div>

      {/* Action Bar: Send Stream to Pi */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
        <div className="text-xs text-sky-300/80 flex items-center gap-2">
          <span className="text-base">🧠</span>
          <span>
            Pi RL Agent model uses outdoor weather forcing to compute indoor RC thermal response.
          </span>
        </div>

        <button
          onClick={handleBroadcastToPi}
          disabled={isBroadcasting}
          className="w-full sm:w-auto px-4 py-2 text-xs font-bold bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 text-white rounded-xl shadow-lg shadow-sky-500/25 border border-sky-300/30 flex items-center justify-center gap-2 transition active:scale-95 cursor-pointer disabled:opacity-50"
        >
          <span>{isBroadcasting ? '📡' : '🚀'}</span>
          <span>{isBroadcasting ? 'Syncing to Pi...' : 'Broadcast Weather Stream to Pi'}</span>
        </button>
      </div>

      {/* Toast Notification */}
      {broadcastStatus && (
        <div className="mt-3 p-2.5 bg-sky-500/20 border border-sky-400/40 text-sky-200 text-xs font-medium rounded-xl text-center animate-fade-in">
          {broadcastStatus}
        </div>
      )}
    </div>
  );
};
