/**
 * Who may see which part of the app, and where they go instead. The router applies these
 * decisions; keeping them here makes every role × profile × readings case testable.
 */

export type Role = 'person' | 'clinician';

/** Route groups: public pages, the two set-up steps, a person's own pages, staff pages, and pages every account shares. */
export type Area = 'public' | 'setup' | 'setup-data' | 'person' | 'staff' | 'shared';

export interface Who {
  role: Role;
  hasProfile: boolean;
}

export type Decision =
  | { kind: 'allow' }
  | { kind: 'redirect'; to: string }
  /** Signed in, but this page is not for this role: show the 403 page. */
  | { kind: 'forbidden' };

const ALLOW: Decision = { kind: 'allow' };

/** Where an account starts: staff on the ward, people without a profile in set-up, else Today. */
export function homePath(who: Who): string {
  if (who.role === 'clinician') return '/ward';
  return who.hasProfile ? '/' : '/setup';
}

/** `who` is null when signed out. */
export function decide(area: Area, who: Who | null): Decision {
  if (who === null) return area === 'public' ? ALLOW : { kind: 'redirect', to: '/welcome' };
  switch (area) {
    case 'public':
      return { kind: 'redirect', to: homePath(who) };
    case 'staff':
      return who.role === 'clinician' ? ALLOW : { kind: 'forbidden' };
    case 'shared':
      return ALLOW;
    case 'setup':
      // Step 1 stays open after a profile exists, so saving it can move on to step 2 without
      // the gate racing the navigation.
      return who.role === 'clinician' ? { kind: 'redirect', to: '/ward' } : ALLOW;
    case 'setup-data':
    case 'person':
      if (who.role === 'clinician') return { kind: 'redirect', to: '/ward' };
      return who.hasProfile ? ALLOW : { kind: 'redirect', to: '/setup' };
  }
}

/** What Today shows for a person with a profile: the add-data choices until the first reading. */
export function todayMode(readings: number): 'add-data' | 'forecast' {
  return readings > 0 ? 'forecast' : 'add-data';
}
