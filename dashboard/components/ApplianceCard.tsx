'use client';

import React from 'react';
import {
  Shield,
  CheckCircle2,
  Clock,
  RotateCcw,
  Power,
} from 'lucide-react';
import { ApplianceState, ActionLevel } from '@/lib/contracts';

interface ApplianceCardProps {
  appliance: ApplianceState;
  onOverride?: (applianceId: string, level: ActionLevel) => void;
  isLoading?: boolean;
}

export function ApplianceCard({
  appliance,
  onOverride,
  isLoading,
}: ApplianceCardProps) {
  const isNecessity = appliance.is_necessity;
  const isRunning = appliance.level === 1;
  const isDeferred =
    appliance.level === 0 &&
    Boolean(appliance.deferred_until);
  const isShed =
    appliance.level === 0 &&
    !appliance.deferred_until;

  return (
    <div
      className={`relative overflow-hidden rounded-xl border p-4 transition-all duration-200 bg-white shadow-sm ${
        isNecessity
          ? 'border-[#d7e3f2] bg-white'
          : isRunning
          ? 'border-[#e5eaf2] bg-white'
          : isDeferred
          ? 'border-[#e5eaf2] bg-white'
          : 'border-[#e5eaf2] bg-[#f6faff] opacity-95'
      }`}
    >
      {/* Top row: Name, Type & Class Badge */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-sm text-[#17365D]">
              {appliance.display_name ||
                appliance.appliance_id}
            </h4>

            {isNecessity && (
              <span className="inline-flex items-center gap-1 rounded bg-[#eaf4ff] px-1.5 py-0.5 font-mono text-[10px] font-bold text-[#0f2d4a] border border-[#e5eaf2]">
                <Shield className="h-2.5 w-2.5" />
                PROTECTED
              </span>
            )}
          </div>

          <p className="text-[11px] text-[#6b7c93] capitalize mt-0.5">
            {appliance.service_class} • ID:{' '}
            <code className="font-mono text-[#0f2d4a]">
              {appliance.appliance_id}
            </code>
          </p>
        </div>

        {/* State Pill */}
        <div>
          {isNecessity ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#d7e3f2] bg-[#eaf4ff] px-2.5 py-1 font-mono text-xs font-bold text-[#0f2d4a]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#a9d0fa] animate-pulse" />
              ON
            </span>
          ) : isRunning ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#e5eaf2] bg-[#eaf4ff] px-2.5 py-1 font-mono text-xs font-bold text-[#0f2d4a]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#eaf4ff]0" />
              RUNNING
            </span>
          ) : isDeferred ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#e5eaf2] bg-[#eaf4ff] px-2.5 py-1 font-mono text-xs font-bold text-[#0f2d4a]">
              <Clock className="h-3 w-3 text-[#6b7c93]" />
              DEFERRED
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#e5eaf2] bg-[#eaf4ff] px-2.5 py-1 font-mono text-xs font-bold text-[#6b7c93]">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
              SHED
            </span>
          )}
        </div>
      </div>

      {/* Middle row: Power Metrics & Verification */}
      <div className="mt-3.5 grid grid-cols-2 gap-2 rounded-lg border border-[#e5eaf2] bg-[#eaf4ff]/50 p-2.5 text-xs">
        <div>
          <span className="block text-[10px] font-medium tracking-wide text-[#6b7c93]">
            SIMULATED POWER
          </span>

          <div className="mt-0.5 flex items-baseline gap-1">
            <span className="font-mono text-sm font-bold text-[#17365D]">
              {isRunning
                ? appliance.power_15min_mean_w.toFixed(1)
                : '0.0'}
            </span>

            <span className="font-mono text-[10px] text-[#6b7c93]">
              W
            </span>
          </div>

          <span className="block text-[9px] text-[#9aa8bd]">
            {appliance.measured_w === null
              ? 'No meter fitted'
              : `${appliance.measured_w} W (meter)`}
          </span>
        </div>

        <div>
          <span className="block text-[10px] font-medium tracking-wide text-[#6b7c93]">
            ACTUATION VERIFIED
          </span>

          <div className="mt-0.5 flex items-center gap-1.5">
            {appliance.actuation_verified ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-[#6b7c93] shrink-0" />
                <span className="font-mono text-xs font-medium text-[#0f2d4a]">
                  GPIO Readback MATCH
                </span>
              </>
            ) : (
              <span className="font-mono text-xs text-[#6b7c93]">
                PENDING VERIFY
              </span>
            )}
          </div>

          <span className="block text-[9px] text-[#9aa8bd]">
            Pin state:{' '}
            {appliance.gpio_state === 1
              ? 'HIGH (1)'
              : 'LOW (0)'}
          </span>
        </div>
      </div>

      {/* Reason line for shed or deferred */}
      {!isNecessity && !isRunning && (
        <div className="mt-2.5 flex items-center justify-between rounded border border-[#e5eaf2] bg-white px-2.5 py-1.5 text-xs">
          <div className="flex items-center gap-1.5 text-[#6b7c93]">
            <span className="text-[11px] font-semibold text-[#6b7c93]">
              Reason:
            </span>

            <span className="font-mono font-bold text-[#0f2d4a] text-[11px]">
              {appliance.shed_reason || 'GRID_PEAK'}
            </span>
          </div>

          {appliance.deferred_until && (
            <span className="font-mono text-[10px] text-[#6b7c93]">
              Resumes: {appliance.deferred_until}
            </span>
          )}
        </div>
      )}

      {/* Action / Control Section:
          CRITICAL INVARIANT:
          Protected appliances must NOT have OFF/SHED controls rendered!
      */}
      <div className="mt-3.5 pt-2 border-t border-[#e5eaf2] flex items-center justify-between">
        {isNecessity ? (
          <div className="flex items-center gap-1.5 text-[11px] text-[#0f2d4a] font-mono">
            <Shield className="h-3 w-3 text-[#6b7c93]" />
            <span>Shield Guarantee: Always Protected</span>
          </div>
        ) : (
          <>
            <span className="text-[11px] text-[#6b7c93]">
              Resident Control:
            </span>

            {isShed || isDeferred ? (
              <button
                type="button"
                onClick={() =>
                  onOverride &&
                  onOverride(appliance.appliance_id, 1)
                }
                disabled={isLoading}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5eaf2] bg-[#eaf4ff] px-3 py-1 font-mono text-xs font-semibold text-[#0f2d4a] hover:bg-[#eaf4ff] hover:border-[#d7e3f2] active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
              >
                <RotateCcw className="h-3 w-3" />
                RESTORE LOAD
              </button>
            ) : (
              <button
                type="button"
                onClick={() =>
                  onOverride &&
                  onOverride(appliance.appliance_id, 0)
                }
                disabled={isLoading}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5eaf2] bg-white px-3 py-1 font-mono text-xs font-semibold text-[#0f2d4a] hover:bg-[#eaf4ff] hover:border-[#d7e3f2] active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
              >
                <Power className="h-3 w-3 text-[#6b7c93]" />
                SHED
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}