'use client';

import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import type { LiveLoadPoint } from '@/lib/useHomeState';

interface PowerChartProps {
  data: LiveLoadPoint[];
  sanctionedLoadKw?: number;
}

export function PowerChart({
  data,
  sanctionedLoadKw = 1.0,
}: PowerChartProps) {
  return (
    <div className="rounded-2xl border border-[#e5eaf2] bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-mono text-sm font-bold tracking-wide text-[#172b4d]">
            Live household load history
          </h3>
          <p className="text-xs text-slate-500">
            Samples accumulated from MQTT runtime telemetry in this browser session.
            Power is estimated from GPIO state and catalogued wattage because no meter is fitted.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[#a9d0fa]" />
            <span className="text-slate-600">Estimated runtime kW</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-blue-800" />
            <span className="text-slate-500">Grid severity</span>
          </div>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="flex h-72 items-center justify-center rounded-xl border border-dashed border-slate-200 text-sm text-slate-500">
          Waiting for runtime samples…
        </div>
      ) : (
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="runtimeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.18} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="peakGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1d4ed8" stopOpacity={0.14} />
                  <stop offset="95%" stopColor="#1d4ed8" stopOpacity={0} />
                </linearGradient>
              </defs>

              <XAxis
                dataKey="time"
                stroke="#94a3b8"
                tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
              />
              <YAxis
                yAxisId="power"
                stroke="#94a3b8"
                tick={{ fill: '#64748b', fontSize: 11, fontFamily: 'monospace' }}
                unit=" kW"
              />
              <YAxis yAxisId="severity" orientation="right" domain={[0, 1]} hide />

              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const load = payload.find((item) => item.dataKey === 'sharpKw')?.value;
                  const severity = payload.find((item) => item.dataKey === 'gridPeakSeverity')?.value;
                  return (
                    <div className="rounded-xl border border-[#e5eaf2] bg-white p-3 shadow-lg text-xs font-mono">
                      <p className="mb-1.5 font-bold text-[#172b4d]">{label} IST</p>
                      <p className="text-[#6b7c93]">
                        Estimated load: <strong>{String(load)} kW</strong>
                      </p>
                      <p className="text-[#0f2d4a]">
                        Grid severity: <strong>{String(severity)}</strong>
                      </p>
                    </div>
                  );
                }}
              />

              <ReferenceLine
                yAxisId="power"
                y={sanctionedLoadKw}
                stroke="#1d4ed8"
                strokeDasharray="4 4"
                label={{
                  value: `Sanctioned Cap (${sanctionedLoadKw} kW)`,
                  fill: '#1e40af',
                  fontSize: 10,
                  position: 'insideTopRight',
                }}
              />

              <Area
                yAxisId="severity"
                type="monotone"
                dataKey="gridPeakSeverity"
                fill="url(#peakGradient)"
                stroke="#1d4ed8"
                strokeWidth={1.5}
              />
              <Area
                yAxisId="power"
                type="monotone"
                dataKey="sharpKw"
                fill="url(#runtimeGradient)"
                stroke="#2563eb"
                strokeWidth={2}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
