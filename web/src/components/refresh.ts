import { createContext, useContext } from 'react';

export interface RefreshState {
  /** Auto-refresh is paused for every page until resumed. */
  paused: boolean;
  setPaused: (paused: boolean) => void;
}

export const RefreshContext = createContext<RefreshState>({ paused: false, setPaused: () => undefined });

export function useRefresh(): RefreshState {
  return useContext(RefreshContext);
}
