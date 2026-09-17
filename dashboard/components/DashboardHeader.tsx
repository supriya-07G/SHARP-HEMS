'use client';

import React from 'react';
import { Zap, Shield, Radio, Eye } from 'lucide-react';
import { SystemConnectionStatus } from '@/lib/contracts';

interface DashboardHeaderProps {
  activeTab: 'resident' | 'discom';
  onTabChange: (tab: 'resident' | 'discom') => void;
  activeScenario: 'normal' | 'peak' | 'outage';
  onScenarioChange: (scenario: 'normal' | 'peak' | 'outage') => void;
  systemStatus: SystemConnectionStatus;
  isPeakActive: boolean;
}

export function DashboardHeader({
  activeTab,
  onTabChange,
  activeScenario,
  onScenarioChange,
  systemStatus,
  isPeakActive,
}: DashboardHeaderProps) {
  const isConnected = systemStatus.status === 'connected';

  return (
    <header className="sticky top-0 z-50 border-b border-[#e5eaf2] bg-white/95 backdrop-blur-xl shadow-sm">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex min-h-16 items-center justify-between gap-4 py-2">

          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#e5eaf2] bg-[#eaf4ff]">
              <Zap className="h-5 w-5 text-[#6b7c93]" />
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-black tracking-wider text-[#17365D]">
                  SHARP
                </span>

                <span className="hidden sm:inline-flex items-center rounded-full border border-[#e5eaf2] bg-[#eaf4ff] px-2 py-0.5 font-mono text-[10px] font-semibold text-[#0f2d4a]">
                  HEMS v2.1
                </span>
              </div>

              <p className="hidden md:block text-[11px] text-[#0f2d4a]/70 font-medium">
                Smart Home Appliance Response Platform
              </p>
            </div>
          </div>

          {/* Navigation */}
          <div className="flex items-center rounded-xl border border-[#e5eaf2] bg-[#eaf4ff] p-1 font-mono text-xs">

            <button
              type="button"
              onClick={() => onTabChange('resident')}
              className={`flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 font-semibold transition-all cursor-pointer ${
                activeTab === 'resident'
                  ? 'border border-[#e5eaf2] bg-[#a9d0fa] text-[#0d3f74] shadow-sm'
                  : 'text-[#0f2d4a] hover:bg-[#eaf4ff]'
              }`}
            >
              <Shield className="h-3.5 w-3.5" />
              Resident View
            </button>

            <button
              type="button"
              onClick={() => onTabChange('discom')}
              className={`relative flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 font-semibold transition-all cursor-pointer ${
                activeTab === 'discom'
                  ? 'border border-[#e5eaf2] bg-[#a9d0fa] text-[#0d3f74] shadow-sm'
                  : 'text-[#0f2d4a] hover:bg-[#eaf4ff]'
              }`}
            >
              <Radio className="h-3.5 w-3.5" />
              DISCOM / Grid

              {isPeakActive && (
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-300 opacity-70" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[#eaf4ff]0" />
                </span>
              )}
            </button>
          </div>

          {/* Right Controls */}
          <div className="flex items-center gap-3">

            {/* Demo Scenario */}
            <div className="hidden lg:flex items-center gap-1 rounded-lg border border-[#e5eaf2] bg-[#eaf4ff] p-1 text-[11px] font-mono">

              <span className="flex items-center gap-1 px-1.5 text-[10px] font-bold uppercase text-[#6b7c93]">
                <Eye className="h-3 w-3" />
                Demo:
              </span>

              <button
                type="button"
                onClick={() => onScenarioChange('normal')}
                className={`rounded px-2 py-0.5 transition-all cursor-pointer ${
                  activeScenario === 'normal'
                    ? 'bg-[#a9d0fa] text-[#0d3f74] font-bold shadow-sm'
                    : 'text-[#6b7c93] hover:bg-[#eaf4ff]'
                }`}
              >
                Normal
              </button>

              <button
                type="button"
                onClick={() => onScenarioChange('peak')}
                className={`rounded px-2 py-0.5 transition-all cursor-pointer ${
                  activeScenario === 'peak'
                    ? 'bg-[#eaf4ff]0 text-white font-bold shadow-sm'
                    : 'text-[#6b7c93] hover:bg-[#eaf4ff]'
                }`}
              >
                Midday Peak (14:05)
              </button>

              <button
                type="button"
                onClick={() => onScenarioChange('outage')}
                className={`rounded px-2 py-0.5 transition-all cursor-pointer ${
                  activeScenario === 'outage'
                    ? 'bg-blue-300 text-[#0f2d4a] font-bold'
                    : 'text-[#6b7c93] hover:bg-[#eaf4ff]'
                }`}
              >
                Outage
              </button>
            </div>

            {/* MQTT Status */}
            <div
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] font-semibold ${
                isConnected
                  ? 'border-[#e5eaf2] bg-[#eaf4ff] text-[#0f2d4a]'
                  : 'border-[#e5eaf2] bg-[#eaf4ff] text-[#0f2d4a]'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isConnected
                    ? 'bg-[#eaf4ff]0 animate-pulse'
                    : 'bg-blue-700'
                }`}
              />

              <span className="hidden sm:inline">MQTT</span>
              {isConnected ? 'LIVE' : 'OFFLINE'}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}