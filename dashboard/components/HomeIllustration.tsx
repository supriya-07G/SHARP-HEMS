'use client';

/**
 * The hero illustration: a modern home in soft blues and sage, with the EV
 * charging on the drive.
 *
 * Built in layers, back to front - sky, distant foliage, mid trees, house,
 * planting, foreground - because depth is what separates an illustration from
 * a diagram. Everything is a tint weight so it never competes with a number.
 *
 * TWO DELIBERATE CHOICES:
 *
 *   No solar panels. The target cohort is 431 households with no inverter and
 *   no solar (D8). Drawing panels would advertise a product this build is not
 *   for, on the one surface a reviewer looks at first.
 *
 *   The EV stays. `ev_charger_01` is appliance 8 on the rig - a deferrable
 *   load, represented by a toy car - so a car on the drive is accurate.
 */

interface Props {
  className?: string;
  /** Hide the car and charge point where the art is small. */
  compact?: boolean;
}

export function HomeIllustration({ className = '', compact = false }: Props) {
  return (
    <svg
      viewBox="0 0 420 240"
      className={className}
      fill="none"
      aria-hidden
      role="presentation"
      preserveAspectRatio="xMidYMax meet"
    >
      <defs>
        <linearGradient id="hi-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#dceafd" />
          <stop offset="100%" stopColor="#f6faff" />
        </linearGradient>
        <linearGradient id="hi-roof" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f4f8fd" />
          <stop offset="100%" stopColor="#dbe7f5" />
        </linearGradient>
        <linearGradient id="hi-glass" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0%" stopColor="#cfe2fa" />
          <stop offset="100%" stopColor="#eaf4ff" />
        </linearGradient>
        <linearGradient id="hi-lawn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#d8ecdd" />
          <stop offset="100%" stopColor="#eaf6ec" />
        </linearGradient>
        <radialGradient id="hi-sun" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="#fef3d3" />
          <stop offset="100%" stopColor="#fef3d3" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* ---- sky ------------------------------------------------------- */}
      <rect width="420" height="240" fill="url(#hi-sky)" />
      <circle cx="330" cy="46" r="34" fill="url(#hi-sun)" />
      <circle cx="330" cy="46" r="13" fill="#fdf0c8" />

      {/* clouds, soft and overlapping */}
      <g fill="#ffffff">
        <g opacity="0.95">
          <ellipse cx="84" cy="44" rx="26" ry="13" />
          <ellipse cx="108" cy="46" rx="18" ry="10" />
          <ellipse cx="64" cy="48" rx="15" ry="8" />
        </g>
        <g opacity="0.8">
          <ellipse cx="258" cy="30" rx="19" ry="9" />
          <ellipse cx="274" cy="32" rx="13" ry="6.5" />
        </g>
      </g>

      {/* ---- distant foliage ------------------------------------------- */}
      <g opacity="0.55">
        <ellipse cx="40" cy="150" rx="46" ry="42" fill="#cfe4d4" />
        <ellipse cx="96" cy="158" rx="38" ry="34" fill="#d7e9db" />
        <ellipse cx="392" cy="150" rx="44" ry="40" fill="#cfe4d4" />
        <ellipse cx="344" cy="160" rx="34" ry="30" fill="#d7e9db" />
      </g>

      {/* ---- mid trees -------------------------------------------------- */}
      <g>
        <rect x="70" y="150" width="5" height="34" rx="2.5" fill="#bcd6c4" />
        <ellipse cx="72.5" cy="140" rx="24" ry="27" fill="#bcdcc6" />
        <ellipse cx="66" cy="132" rx="16" ry="18" fill="#d2e9d8" />

        <rect x="352" y="154" width="4.5" height="30" rx="2.25" fill="#bcd6c4" />
        <ellipse cx="354" cy="145" rx="20" ry="23" fill="#bcdcc6" />
        <ellipse cx="349" cy="139" rx="13" ry="15" fill="#d2e9d8" />
      </g>

      {/* ---- lawn ------------------------------------------------------- */}
      <path d="M0 186 Q120 172 210 182 T420 176 L420 240 L0 240 Z" fill="url(#hi-lawn)" />
      <path d="M0 200 Q140 190 240 198 T420 192 L420 240 L0 240 Z"
            fill="#e4f3e8" opacity="0.8" />

      {/* ---- house ------------------------------------------------------ */}
      <g>
        {/* soft ground shadow */}
        <ellipse cx="214" cy="186" rx="96" ry="9" fill="#cfe0ef" opacity="0.5" />

        {/* garage wing */}
        <rect x="256" y="146" width="62" height="40" rx="4" fill="#ffffff" />
        <rect x="256" y="146" width="62" height="40" rx="4" fill="none"
              stroke="#e0e9f3" strokeWidth="1.2" />
        <rect x="266" y="158" width="42" height="28" rx="3" fill="#e7eef7" />
        <g stroke="#d5e1ee" strokeWidth="1">
          <path d="M266 166h42M266 173h42M266 180h42" />
        </g>

        {/* main pitched volume */}
        <path d="M120 152 L176 96 L232 152 Z" fill="url(#hi-roof)" />
        <path d="M120 152 L176 96 L232 152" fill="none" stroke="#cfdcea"
              strokeWidth="1.3" strokeLinejoin="round" />
        <rect x="128" y="148" width="96" height="38" rx="4" fill="#ffffff" />
        <rect x="128" y="148" width="96" height="38" rx="4" fill="none"
              stroke="#e0e9f3" strokeWidth="1.2" />

        {/* full-height glazing - the bit that says "modern house" */}
        <rect x="138" y="154" width="34" height="32" rx="3" fill="url(#hi-glass)" />
        <rect x="138" y="154" width="34" height="32" rx="3" fill="none"
              stroke="#c4daf3" strokeWidth="1" />
        <path d="M155 154v32" stroke="#dcebfb" strokeWidth="1.2" />

        {/* warm windows: somebody is home, and the lights stay on */}
        <rect x="182" y="156" width="16" height="13" rx="2.5" fill="#fef6e2"
              stroke="#f7e3ae" strokeWidth="1" />
        <rect x="204" y="156" width="14" height="13" rx="2.5" fill="#fef6e2"
              stroke="#f7e3ae" strokeWidth="1" />

        {/* door */}
        <rect x="184" y="172" width="16" height="14" rx="2" fill="#e7eef7"
              stroke="#d5e1ee" strokeWidth="1" />

        {/* gable window */}
        <path d="M176 112 L196 132 L156 132 Z" fill="#e8f2fd" stroke="#cfe2fa"
              strokeWidth="1" strokeLinejoin="round" />
      </g>

      {/* ---- drive, EV and charge point --------------------------------- */}
      {!compact && (
        <g>
          <path d="M252 186 q34 2 62 0 l6 12 q-40 3 -74 0 Z" fill="#edf2f8" />

          {/* charge point - ev_charger_01, appliance 8 on the rig */}
          <rect x="247" y="164" width="7" height="16" rx="2.5" fill="#cfe2fa" />
          <circle cx="250.5" cy="169" r="1.8" fill="#8fd3b4" />

          {/* car */}
          <g>
            <ellipse cx="292" cy="194" rx="27" ry="4" fill="#cfe0ef" opacity="0.6" />
            <path d="M270 188 q3 -11 10 -13 h20 q8 2 13 13 z" fill="#ffffff" />
            <path d="M270 188 q3 -11 10 -13 h20 q8 2 13 13" fill="none"
                  stroke="#dbe7f5" strokeWidth="1.1" strokeLinejoin="round" />
            <path d="M281 177 h17 q5 1 8 8 h-25 z" fill="#dceafd" opacity="0.85" />
            <circle cx="279" cy="189" r="4" fill="#c6d6e6" />
            <circle cx="279" cy="189" r="1.6" fill="#eef4fa" />
            <circle cx="303" cy="189" r="4" fill="#c6d6e6" />
            <circle cx="303" cy="189" r="1.6" fill="#eef4fa" />
          </g>
        </g>
      )}

      {/* ---- planting --------------------------------------------------- */}
      <g>
        <ellipse cx="116" cy="182" rx="16" ry="12" fill="#c8e3cf" />
        <ellipse cx="104" cy="185" rx="11" ry="8" fill="#d8ecdd" />
        <ellipse cx="238" cy="183" rx="13" ry="10" fill="#c8e3cf" />
        <ellipse cx="330" cy="184" rx="14" ry="10" fill="#d8ecdd" />
      </g>

      {/* ---- foreground leaves, for depth ------------------------------- */}
      <g opacity="0.75">
        <path d="M0 240 q18 -30 8 -52 q22 16 18 52 z" fill="#bcdcc6" />
        <path d="M10 240 q22 -22 34 -26 q-8 18 -18 26 z" fill="#cfe7d6" />
        <path d="M420 240 q-20 -26 -10 -48 q-24 14 -20 48 z" fill="#bcdcc6" />
      </g>
    </svg>
  );
}
