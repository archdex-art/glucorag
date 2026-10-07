import { createContext, useContext } from 'react';
import type { ApiClient } from '../api/client';
import type { Account } from '../api/types';

export interface AuthState {
  /** The signed-in account; null when signed out or still loading. */
  account: Account | null;
  /** `loading` until `GET /auth/me` answers on boot; `error` when the service is unreachable. */
  phase: 'loading' | 'ready' | 'error';
  /** Why the boot check failed (only in `error`). */
  bootError: unknown;
  /** One message for the page a signed-out visitor lands on (session ended, signed out, deleted). */
  notice: string | null;
  /** Where the gates send a signed-out visitor after a session ends; null = Welcome. */
  signedOutPath: string | null;
  /** The API client. It works signed out too; requests that need a session then answer 401. */
  client: ApiClient;
  signIn: (email: string, password: string) => Promise<Account>;
  signUp: (email: string, password: string) => Promise<Account>;
  /** Ends the session and lands on sign-in. */
  signOut: () => Promise<void>;
  /** Re-reads `GET /auth/me` (after set-up, a unit change, or to retry the boot check). */
  refresh: () => Promise<Account | null>;
  /** Forget the account locally after the service already ended it (account deleted). */
  clear: (notice?: string, landing?: string) => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

export function useApi(): ApiClient {
  return useAuth().client;
}

/** The signed-in account; only valid below the router's sign-in gate. */
export function useAccount(): Account {
  const { account } = useAuth();
  if (!account) throw new Error('useAccount called without a session');
  return account;
}
