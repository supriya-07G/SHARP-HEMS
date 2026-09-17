/**
 * The three roles this build ships.
 *
 * There is NO authentication here, by decision, so the switcher is a plain
 * client-side toggle for the demo. That is safe only because nothing in this
 * build can reach real hardware.
 *
 * Before this is ever exposed beyond a demo it needs real auth: a grid
 * controller declaring a peak sheds load in every home that is listening, and
 * that must never be a URL anyone can visit.
 */

export type Role = 'resident' | 'grid' | 'technical';

export const ROLES: Array<{ id: Role; label: string; description: string }> = [
  {
    id: 'resident',
    label: 'Home resident',
    description: 'Sees their appliances, overrides decisions, reads their bill.',
  },
  {
    id: 'grid',
    label: 'Grid controller',
    description:
      'Declares peak events. Can restrict luxury loads; can never touch a ' +
      'critical load in any home.',
  },
  {
    id: 'technical',
    label: 'Technical',
    description:
      'Model and registry, device health, and settings such as the notice ' +
      'given before a peak.',
  },
];

export const DEFAULT_ROLE: Role = 'resident';

/** Where each role lives. Kept here so the nav and the routes cannot drift. */
export const ROLE_PATH: Record<Role, string> = {
  resident: '/resident',
  grid: '/grid',
  technical: '/technical',
};
