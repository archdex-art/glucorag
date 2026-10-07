import { describe, expect, it } from 'vitest';
import { decide, homePath, todayMode, type Area, type Who } from './access';

const person = (hasProfile: boolean): Who => ({ role: 'person', hasProfile });
const clinician: Who = { role: 'clinician', hasProfile: false };
const AREAS: Area[] = ['public', 'setup', 'setup-data', 'person', 'staff', 'shared'];

describe('where an account starts', () => {
  it('sends clinicians to the ward, people without a profile to set-up, else Today', () => {
    expect(homePath(clinician)).toBe('/ward');
    expect(homePath({ role: 'clinician', hasProfile: true })).toBe('/ward');
    expect(homePath(person(false))).toBe('/setup');
    expect(homePath(person(true))).toBe('/');
  });

  it('shows the add-data choices on Today until the first reading', () => {
    expect(todayMode(0)).toBe('add-data');
    expect(todayMode(1)).toBe('forecast');
  });
});

describe('route decisions', () => {
  it('lets signed-out visitors see only the public pages', () => {
    for (const area of AREAS) {
      expect(decide(area, null)).toEqual(area === 'public' ? { kind: 'allow' } : { kind: 'redirect', to: '/welcome' });
    }
  });

  it('moves signed-in accounts off the public pages to their start', () => {
    expect(decide('public', person(false))).toEqual({ kind: 'redirect', to: '/setup' });
    expect(decide('public', person(true))).toEqual({ kind: 'redirect', to: '/' });
    expect(decide('public', clinician)).toEqual({ kind: 'redirect', to: '/ward' });
  });

  it('keeps a person without a profile in set-up step 1', () => {
    const who = person(false);
    expect(decide('setup', who)).toEqual({ kind: 'allow' });
    expect(decide('setup-data', who)).toEqual({ kind: 'redirect', to: '/setup' });
    expect(decide('person', who)).toEqual({ kind: 'redirect', to: '/setup' });
    expect(decide('shared', who)).toEqual({ kind: 'allow' });
  });

  it('lets a person with a profile use their pages and both set-up steps', () => {
    const who = person(true);
    expect(decide('setup', who)).toEqual({ kind: 'allow' });
    expect(decide('setup-data', who)).toEqual({ kind: 'allow' });
    expect(decide('person', who)).toEqual({ kind: 'allow' });
  });

  it('shows a person the 403 page on staff pages, with or without a profile', () => {
    expect(decide('staff', person(true))).toEqual({ kind: 'forbidden' });
    expect(decide('staff', person(false))).toEqual({ kind: 'forbidden' });
  });

  it('gives clinicians the staff pages and Settings, and sends them from personal pages to the ward', () => {
    expect(decide('staff', clinician)).toEqual({ kind: 'allow' });
    expect(decide('shared', clinician)).toEqual({ kind: 'allow' });
    for (const area of ['setup', 'setup-data', 'person'] as const) {
      expect(decide(area, clinician)).toEqual({ kind: 'redirect', to: '/ward' });
    }
  });
});
