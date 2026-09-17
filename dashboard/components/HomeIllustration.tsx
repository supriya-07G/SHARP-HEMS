'use client';

/**
 * The house from the style guide, drawn in palette tints.
 *
 * Decoration, deliberately quiet: it sits behind the greeting and must never
 * compete with a number. Everything here is a tint weight, and it is hidden on
 * small screens where the space belongs to content.
 *
 * No solar panels. The target cohort is 431 households with no inverter and no
 * solar (D8), so drawing panels on the house would advertise a product this
 * build is not for.
 */

export function HomeIllustration({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 320 150"
      className={className}
      fill="none"
      aria-hidden
      role="presentation"
    >
      {/* sky wash */}
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#eaf4ff" />
          <stop offset="100%" stopColor="#f6faff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="roof" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#a9d0fa" />
          <stop offset="100%" stopColor="#8fc1f7" />
        </linearGradient>
      </defs>

      <rect width="320" height="150" fill="url(#sky)" />

      {/* clouds */}
      <g fill="#ffffff" opacity="0.9">
        <ellipse cx="54" cy="34" rx="20" ry="11" />
        <ellipse cx="72" cy="34" rx="14" ry="8" />
        <ellipse cx="250" cy="26" rx="16" ry="9" />
        <ellipse cx="264" cy="27" rx="11" ry="6.5" />
      </g>

      {/* trees */}
      <g>
        <rect x="36" y="104" width="4" height="18" rx="2" fill="#cfe2fa" />
        <ellipse cx="38" cy="99" rx="15" ry="17" fill="#d9ecf9" />
        <ellipse cx="38" cy="93" rx="11" ry="12" fill="#eaf4ff" />
        <rect x="286" y="108" width="3.5" height="14" rx="1.75" fill="#cfe2fa" />
        <ellipse cx="287.5" cy="103" rx="12" ry="14" fill="#d9ecf9" />
      </g>

      {/* house */}
      <g>
        {/* roof */}
        <path d="M96 84 L160 44 L224 84 Z" fill="url(#roof)" />
        {/* body */}
        <rect x="108" y="82" width="104" height="42" rx="5" fill="#ffffff"
              stroke="#e5eaf2" strokeWidth="1.5" />
        {/* door */}
        <rect x="150" y="98" width="20" height="26" rx="3" fill="#eaf4ff"
              stroke="#cfe2fa" strokeWidth="1.2" />
        <circle cx="165" cy="111" r="1.4" fill="#a9d0fa" />
        {/* windows - warm, because somebody is home and the lights stay on */}
        <rect x="120" y="94" width="18" height="14" rx="3" fill="#fef8e9"
              stroke="#fde4a6" strokeWidth="1.2" />
        <rect x="182" y="94" width="18" height="14" rx="3" fill="#fef8e9"
              stroke="#fde4a6" strokeWidth="1.2" />
        {/* chimney */}
        <rect x="196" y="56" width="10" height="18" rx="2" fill="#cfe2fa" />
      </g>

      {/* ground */}
      <path d="M0 124 Q80 116 160 124 T320 122 L320 150 L0 150 Z" fill="#eaf4ff" />

      {/* a small mint pulse: the house is connected and being served */}
      <g>
        <circle cx="160" cy="34" r="4" fill="#b6ecd5" />
        <circle cx="160" cy="34" r="8" fill="none" stroke="#b6ecd5"
                strokeWidth="1.5" opacity="0.55" />
      </g>
    </svg>
  );
}
