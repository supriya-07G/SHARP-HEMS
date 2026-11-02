/**
 * The four house scenarios the Pi's scenario service can apply. Names must
 * match SCENARIOS in hardware/mock_rl_state.py.
 *
 * The grid peak itself is never set here: it is declared by the Grid
 * Controller. A grid scenario only sets up the house for one.
 */

export type DemoScenarioId =
  | 'normal'
  | 'household_peak'
  | 'grid_peak'
  | 'grid_and_household_peak';

export interface DemoScenario {
  id: DemoScenarioId;
  label: string;
  description: string;
  /** The grid peak still has to be declared on Grid Control. */
  needsGridPeak: boolean;
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: 'normal',
    label: 'Normal',
    description: 'Fridge, TV, fan and lights on. Nothing is shed.',
    needsGridPeak: false,
  },
  {
    id: 'household_peak',
    label: 'Household peak',
    description: 'All on, then luxury loads shed in this house only.',
    needsGridPeak: false,
  },
  {
    id: 'grid_peak',
    label: 'Grid peak',
    description: 'All on; luxury loads shed once a grid peak is declared.',
    needsGridPeak: true,
  },
  {
    id: 'grid_and_household_peak',
    label: 'Grid + household peak',
    description: 'All on; luxury shed at once, and through the grid peak.',
    needsGridPeak: true,
  },
];

export function isDemoScenario(value: unknown): value is DemoScenarioId {
  return DEMO_SCENARIOS.some((s) => s.id === value);
}

/** What the Pi's scenario service reports on home/<house>/scenario/active. */
export interface ScenarioActive {
  schema_version: 'sharp_scenario_active_v1';
  house_id: string;
  scenario: string;
  household_peak: boolean;
  expects_grid_peak: boolean;
  applied_at: string;
  republish_seconds: number;
}

export function isScenarioActive(value: unknown): value is ScenarioActive {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<ScenarioActive>;
  return (
    v.schema_version === 'sharp_scenario_active_v1' &&
    typeof v.scenario === 'string' &&
    typeof v.applied_at === 'string'
  );
}
