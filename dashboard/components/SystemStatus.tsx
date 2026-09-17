'use client';

import React from 'react';
import {
  Wifi,
  WifiOff,
  RefreshCw,
  ShieldAlert,
  Cpu,
} from 'lucide-react';
import { SystemConnectionStatus } from '@/lib/contracts';

interface SystemStatusProps {
  status: SystemConnectionStatus;
  houseId: string;
  gridAbsent: boolean;
  operatingMode: string;
}

export function SystemStatus({
  status,
  houseId,
  gridAbsent,
  operatingMode,
}: SystemStatusProps) {
  const isConnected = status.status === 'connected';

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#e5eaf2] bg-white px-4 py-2.5 shadow-sm text-xs">

      <div className="flex flex-wrap items-center gap-4">

        {/* Connection */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {isConnected ? (
              <>
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-300 opacity-50" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#eaf4ff]0" />
              </>
            ) : (
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-700" />
            )}
          </span>

          <span className="flex items-center gap-1.5 font-mono font-medium text-[#0f2d4a]">
            {isConnected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-[#6b7c93]" />
                Connected
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-[#0f2d4a]" />
                MQTT DISCONNECTED (Retained State)
              </>
            )}
          </span>
        </div>

        {/* Data Age */}
        <div className="flex items-center gap-1 font-mono text-[#6b7c93]">
          <RefreshCw className="h-3 w-3 text-[#9aa8bd]" />

          <span>Age:</span>

          <span
            className={`font-semibold ${
              status.data_age_seconds > 30
                ? 'text-[#0f2d4a]'
                : 'text-[#0f2d4a]'
            }`}
          >
            {status.data_age_seconds}s
          </span>
        </div>

        {/* House Node */}
        <div className="hidden sm:flex items-center gap-1 font-mono text-[#6b7c93]">
          <Cpu className="h-3.5 w-3.5 text-[#6b7c93]" />

          <span>Node:</span>

          <span className="font-semibold text-[#0f2d4a]">
            {houseId}
          </span>
        </div>

        {/* Operating Mode */}
        <div className="hidden md:flex items-center gap-1.5 font-mono text-[#6b7c93]">
          <span>Mode:</span>

          <span
            className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase ${
              gridAbsent
                ? 'border border-[#d7e3f2] bg-[#eaf4ff] text-[#0f2d4a]'
                : 'border border-[#e5eaf2] bg-[#eaf4ff] text-[#0f2d4a]'
            }`}
          >
            {operatingMode.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Right Status */}
      <div className="flex items-center gap-3">

        {gridAbsent && (
          <div className="flex items-center gap-1.5 rounded-md border border-[#d7e3f2] bg-[#eaf4ff] px-2 py-0.5 font-mono text-[11px] font-semibold text-[#0f2d4a] animate-pulse">
            <ShieldAlert className="h-3 w-3" />
            GRID ABSENT: ISLANDED BATTERY
          </div>
        )}

        <span className="hidden lg:inline text-[11px] text-[#9aa8bd] font-mono">
          WSS:443 (TLS Encrypted)
        </span>
      </div>
    </div>
  );
}