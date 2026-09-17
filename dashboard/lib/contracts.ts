/**
 * SHARP Data Contracts (Frozen v2)
 *
 * Source of truth: docs/DASHBOARD_SPECIFICATION.md §5, docs/INTEGRATION_GUIDE.md §1.5,
 * and docs/GRID_CONTROLLER_AND_TARIFF.md.
 *
 * Action levels:
 *  0 = OFF       (shed luxury loads only)
 *  1 = ON        (full power)
 *  2 = REDUCED   (reserved/dimmed, not offered in current binary build)
 */

export type ActionLevel = 0 | 1 | 2;

export type OperatingMode =
  | 'grid_import'
  | 'self_sufficient'
  | 'islanded_outage';

export type ServiceClass =
  | 'critical'
  | 'thermostatic'
  | 'deferrable'
  | 'interruptible';

export interface ApplianceState {
  appliance_id: string;
  appliance_type: string;
  service_class: ServiceClass;
  is_necessity: boolean;
  supports_reduced: boolean;
  level: ActionLevel;
  power_15min_mean_w: number;
  measured_w: number | null;
  gpio_state: 0 | 1;
  actuation_verified: boolean;
  remaining_service_hours: number;

  /**
   * The occupant is asking for this appliance NOW.
   *
   * LOAD-BEARING. Protection is conditional on it: SHARP never sheds a critical
   * load the occupant wants, but the occupant may always switch their own
   * appliance off. Without this field the UI cannot tell those apart and ends
   * up refusing the resident control of their own fan.
   */
  occupant_wants: boolean;

  /**
   * A grid peak currently forbids energising this circuit.
   *
   * LOAD-BEARING. Without it the UI leaves "turn on" enabled during a peak, the
   * Pi refuses, and nothing visibly happens - a silent failure, which is the
   * worst kind on a demo.
   */
  peak_locked_out: boolean;

  display_name?: string;
  shed_reason?: string | null;
  deferred_until?: string | null;
}

export interface HomeState {
  house_id: string;
  timestamp_ist: string;
  aggregate_power_kw: number;
  background_load_kw: number;
  sanctioned_load_kw: number;
  indoor_temperature_c: number;
  outdoor_temperature_c: number;
  occupancy_adult_home_fraction: number;
  attention_available: boolean;
  marginal_tariff_inr_kwh: number;
  month_to_date_kwh: number;
  grid_peak_severity: number;
  operating_mode: OperatingMode;
  battery_state_of_charge: number;
  grid_absent: boolean;
  appliances: ApplianceState[];
  data_age_seconds?: number;
  step_id?: number;
}

export interface PeakEvent {
  event_id: string;
  sequence: number;
  region: string;
  severity: number;
  declared_at: string;
  expires_at: string;
  reason: string;
  is_active: boolean;
  homes_responding?: number;
  mw_relieved?: number;
}

export interface Intent {
  command_id: string;
  proposed: Record<string, ActionLevel>;
  executed: Record<string, ActionLevel>;
  shield_reasons: Record<string, string[]>;
  policy_source: string;
  decision_latency_ms: number;
}

export interface CommandAck {
  command_id: string;
  appliance_id: string;
  accepted: boolean;
  applied_level: ActionLevel;
  rejected_reason: string | null;
  gpio_state: 0 | 1;
  measured_w: number | null;
  verification:
    | 'MATCH'
    | 'MISMATCH_STILL_DRAWING'
    | 'MISMATCH_NOT_DRAWING'
    | 'MISMATCH_WRONG_LEVEL'
    | 'NO_METER';
  acked_at: string;
  latency_ms: number;
}

export interface OverrideRequest {
  override_id: string;
  appliance_id: string;
  requested_level: ActionLevel;
  issued_at: string;
  user_id: string;
  client_latency_ms: number;
}

export interface SystemConnectionStatus {
  status: 'connected' | 'disconnected' | 'reconnecting';
  data_age_seconds: number;
  broker_endpoint: string;
  last_verified_at: string;
  is_fallback: boolean;
}

/**
 * MQTT feed status used by the browser dashboard.
 *
 * This is the connection/data layer status and is separate from
 * SystemConnectionStatus, which is the dashboard-facing status contract.
 */
export interface Feed {
  status: 'live' | 'stale' | 'connecting' | 'offline';
  dataAgeSeconds: number;
  state: HomeState | null;
  intent: Intent | null;
}
// ---------------------------------------------------------------------------
// FROZEN VOCABULARY — do not edit without changing the Pi to match
// ---------------------------------------------------------------------------

/**
 * The ten appliance ids. Frozen: the Pi, the rig and this app must agree.
 * A typo here is a silent failure - nothing throws, the appliance just never
 * updates.
 */
export const APPLIANCE_IDS = [
  'ceiling_fan_01',
  'table_fan_01',
  'led_bulb_01',
  'led_tube_01',
  'refrigerator_01',
  'air_conditioner_01',
  'washing_machine_01',
  'ev_charger_01',
  'television_01',
  'mixer_grinder_01',
] as const;

export type ApplianceId = (typeof APPLIANCE_IDS)[number];

/** Closed set. The Pi will never send anything else; do not invent strings. */
export type RejectedReason =
  | 'necessity_mask'
  | 'compressor_protection'
  | 'cycle_active'
  | 'min_on_steps'
  | 'min_off_steps'
  | 'command_expired'
  | 'level_not_supported'
  | 'peak_lockout'
  | 'watchdog_hold';

/** A refusal is evidence, not an error. Render it in words the resident reads. */
export const REJECTION_TEXT: Record<RejectedReason, string> = {
  necessity_mask: 'Essential load — cannot be shed',
  compressor_protection: 'Compressor needs 3 minutes before restarting',
  cycle_active: 'Mid-cycle — cannot be interrupted',
  min_on_steps: 'Minimum run time not yet reached',
  min_off_steps: 'Minimum off time not yet reached',
  command_expired: 'Command arrived too late',
  level_not_supported: 'This appliance has no such level',
  peak_lockout: 'Unavailable during grid peak',
  watchdog_hold: 'No valid command — holding last safe state',
};

// ---------------------------------------------------------------------------
// The rules, as functions. Keep them here, not scattered through components -
// a rule that lives in one component is a rule the next component forgets.
// ---------------------------------------------------------------------------

/**
 * Whether to show an off control at all.
 *
 * A critical appliance THE OCCUPANT IS USING renders with NO off control - not
 * greyed, absent. No such action exists anywhere in the system.
 *
 * The condition matters. A fridge at 3am that nobody is asking for may be
 * switched off by the resident: the shield protects essential service from the
 * CONTROLLER, never from the person who lives there.
 */
export function canShowOffControl(a: ApplianceState): boolean {
  return !(a.is_necessity && a.occupant_wants);
}

/**
 * Whether an override can be attempted right now.
 *
 * A phone override can fail silently where a wall switch cannot, so disable the
 * control and say why rather than accepting a tap that will never arrive.
 */
export function overrideAvailable(
  a: ApplianceState,
  live: boolean,
): { enabled: boolean; reason?: string } {
  if (!live) return { enabled: false, reason: 'No connection' };
  if (a.peak_locked_out) {
    return { enabled: false, reason: REJECTION_TEXT.peak_lockout };
  }
  if (!canShowOffControl(a)) {
    return { enabled: false, reason: REJECTION_TEXT.necessity_mask };
  }
  return { enabled: true };
}

/** Peak avoided, expressed the way a DISCOM and a citizen both understand. */
export function homesNotBlackedOut(peakCutPercent: number): string {
  return `equivalent to ${peakCutPercent.toFixed(1)} homes in 100 not blacked out`;
}

// ---------------------------------------------------------------------------
// Credits — paying to keep a luxury load through a peak
// ---------------------------------------------------------------------------

/**
 * What it costs to keep one load running through one event, and what the
 * household has to spend.
 *
 * This is Critical Peak Pricing with OPT-OUT, and three of its design rules
 * are load-bearing:
 *
 *   Events are capped (10-15 a year, published in advance). Unlimited events
 *   would let a DISCOM suppress luxury indefinitely, which breaks the promise
 *   that supply is for everyone.
 *
 *   Participation is COMPENSATED. A household that never opts out must end the
 *   year paying LESS. Without that it is a penalty, and a regulator rejects it.
 *
 *   The default is to shed. Measured participation is 85 % for opt-out against
 *   28 % for opt-in, so the default carries the programme.
 *
 * Every amount here is a PROPOSAL under the Electricity (Rights of Consumers)
 * Amendment Rules 2023. APCPDCL has no domestic time-of-day rate today, so
 * these are never presented as charges this utility currently issues.
 */
export interface CreditAccount {
  /** Credits available to spend on keeping luxury loads on. */
  balance: number;
  /** Credits one appliance costs for one event. */
  cost_to_keep: number;
  /** Events this household opted out of, this billing month. */
  opted_out_this_month: number;
  /** Events participated in - these earn the relief credit. */
  participated_this_month: number;
  /** Programme cap on events per year. */
  events_capped_per_year: number;
}

/** An override that spent credits. THE reward model's training label. */
export interface OverrideEvent {
  override_id: string;
  house_id: string;
  appliance_id: ApplianceId | string;
  requested_level: ActionLevel;
  /**
   * Milliseconds from the notice appearing to the tap.
   *
   * NOT a UI timing. This is the graded preference signal: a fast override
   * means the load mattered more. Instrument it properly - timestamp,
   * appliance, the agent's prior action, and the context state - rather than
   * treating it as a click.
   */
  client_latency_ms: number | null;
  credits_spent: number;
  /** True where a presence sensor confirms somebody could have objected. */
  occupancy_confirmed: boolean;
  issued_at: string;
  /** What the shield did with it. Null until the Pi answers. */
  applied_level: ActionLevel | null;
  rejected_reason: RejectedReason | null;
}
