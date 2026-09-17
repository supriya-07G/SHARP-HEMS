'use client';

import React from 'react';

/**
 * The headline stat card: pastel icon tile, one big number, one chip.
 *
 * Two rules from the style guide are enforced here rather than left to the
 * caller. The fill is always a tint and the text on it is always ink weight -
 * pastel text on a pastel fill is what makes a soft palette unreadable. And
 * `note` is where a simulated value gets said out loud.
 */

export type Tone = 'blue' | 'mint' | 'yellow' | 'red' | 'slate';

const TINT: Record<Tone, string> = {
  blue: 'var(--primary-tint)',
  mint: 'var(--mint-tint)',
  yellow: 'var(--yellow-tint)',
  red: 'var(--red-tint)',
  slate: '#f1f4f9',
};

const INK: Record<Tone, string> = {
  blue: 'var(--primary-ink)',
  mint: 'var(--mint-ink)',
  yellow: 'var(--yellow-ink)',
  red: 'var(--red-ink)',
  slate: 'var(--slate)',
};

/** Legacy variant names, mapped onto the style-guide tones. Kept so the
 *  components written against the earlier API keep rendering; new code should
 *  pass `tone`. */
const LEGACY_TONE: Record<string, Tone> = {
  cyan: 'blue', blue: 'blue', emerald: 'mint', green: 'mint', mint: 'mint',
  amber: 'yellow', yellow: 'yellow', red: 'red', rose: 'red',
  slate: 'slate', gray: 'slate', neutral: 'slate',
};

interface Props {
  /** Preferred. */
  label?: string;
  value: string | number;
  unit?: string;
  note?: string;
  tone?: Tone;
  chip?: { text: string; tone?: Tone };
  /** A node, or a component such as a Lucide icon. */
  icon?: React.ReactNode | React.ComponentType<{ size?: number }>;

  /** Legacy spellings. */
  title?: string;
  subtext?: string;
  variant?: string;
  badge?: { text: string; type?: string };
}

export function StatCard({
  label, value, unit, note, tone, chip, icon, title, subtext, variant, badge,
}: Props) {
  const heading = label ?? title ?? '';
  const footnote = note ?? subtext;
  const resolvedTone: Tone = tone ?? LEGACY_TONE[variant ?? ''] ?? 'blue';
  const resolvedChip = chip ?? (badge
    ? { text: badge.text, tone: LEGACY_TONE[badge.type ?? ''] ?? resolvedTone }
    : undefined);

  // An icon may arrive as an element (<Zap />) or as a component (Zap). Lucide
  // components are forwardRef OBJECTS, not functions, so a typeof check misses
  // them and React then tries to render the object itself. Test for an element
  // instead, and construct anything that is not one.
  const glyph = icon == null || React.isValidElement(icon)
    ? icon
    : React.createElement(icon as React.ComponentType<{ size?: number }>, { size: 20 });
  return (
    <div className="card card-lift p-4">
      <div className="flex items-start gap-3">
        <span className="tile"
              style={{ background: TINT[resolvedTone], color: INK[resolvedTone] }}>
          {glyph}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[12.5px] font-medium" style={{ color: 'var(--slate)' }}>
            {heading}
          </p>
          <p className="metric mt-1 truncate">
            {value}
            {unit && (
              <span className="ml-1 text-[14px] font-medium"
                    style={{ color: 'var(--slate)' }}>
                {unit}
              </span>
            )}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {resolvedChip && (
              <span className={`chip chip-${resolvedChip.tone ?? resolvedTone}`}>
                {resolvedChip.text}
              </span>
            )}
            {footnote && (
              <span className="text-[11px]" style={{ color: 'var(--slate-soft)' }}>
                {footnote}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
