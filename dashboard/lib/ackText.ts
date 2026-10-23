/**
 * Words for a command result. A refusal is evidence, not an error - never
 * show a resident a raw code.
 *
 * Two kinds of "not applied":
 *   - the Pi refused it (codes in REJECTION_TEXT, from the shield), or
 *   - it never reached a Pi that could answer (codes set by this dashboard).
 */

import { CommandAck, REJECTION_TEXT, RejectedReason } from './contracts';

/** Set by the dashboard when no Pi decision exists. */
export const LOCAL_FAILURE_TEXT: Record<string, string> = {
  PI_NO_RESPONSE:
    'No reply from the Raspberry Pi — it may be offline. Nothing was switched.',
  BROKER_UNAVAILABLE:
    'Could not reach the message broker. Nothing was sent to the Pi.',
  RUNTIME_UNAVAILABLE:
    'No live data from the house yet. Nothing was sent to the Pi.',
};

export function isPiRefusal(code: string | null): code is RejectedReason {
  return code !== null && code in REJECTION_TEXT;
}

export function ackTitle(ack: CommandAck): string {
  if (ack.accepted) return 'COMMAND ACCEPTED';
  return isPiRefusal(ack.rejected_reason) ? 'REFUSED BY THE PI' : 'NOT APPLIED';
}

export function ackReasonText(ack: CommandAck): string {
  const code = ack.rejected_reason;
  if (isPiRefusal(code)) return REJECTION_TEXT[code];
  if (code && code in LOCAL_FAILURE_TEXT) return LOCAL_FAILURE_TEXT[code];
  return 'The command was not applied.';
}
