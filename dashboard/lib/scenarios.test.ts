import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { DEMO_SCENARIOS, isDemoScenario, isScenarioActive } from './scenarios';

describe('demo scenarios', () => {
  it('match the scenario names the Pi knows', () => {
    // A typo here would be a silent failure: the Pi ignores unknown names.
    const pySource = readFileSync(
      path.resolve(__dirname, '../../hardware/mock_rl_state.py'),
      'utf8',
    );
    for (const s of DEMO_SCENARIOS) {
      expect(pySource).toContain(`"${s.id}": {`);
    }
  });

  it('accepts only the four scenarios', () => {
    expect(isDemoScenario('household_peak')).toBe(true);
    expect(isDemoScenario('peak')).toBe(false);
    expect(isDemoScenario('anything')).toBe(false);
    expect(isDemoScenario(undefined)).toBe(false);
  });

  it('recognises the service report', () => {
    expect(isScenarioActive({
      schema_version: 'sharp_scenario_active_v1',
      house_id: 'demo', scenario: 'normal',
      household_peak: false, expects_grid_peak: false,
      applied_at: '2026-11-02T12:00:00+05:30', republish_seconds: 30,
    })).toBe(true);
    expect(isScenarioActive({ scenario: 'normal' })).toBe(false);
  });
});
