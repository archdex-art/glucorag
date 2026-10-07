import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiClient } from '../api/client';
import { SESSION_ENDED, UnauthorizedError } from '../api/errors';
import type { Account } from '../api/types';
import { forgetSource } from '../lib/source';
import { AuthContext, type AuthState } from './context';

type Boot = { account: Account | null } | { error: unknown };

/** `GET /auth/me` as a result: an account, signed out (null), or why the service could not answer. */
async function readAccount(client: ApiClient): Promise<Boot> {
  try {
    return { account: await client.account() };
  } catch (err) {
    return err instanceof UnauthorizedError ? { account: null } : { error: err };
  }
}

/**
 * Holds the session: loads `GET /auth/me` on boot and turns any later 401 into a return to
 * sign-in. Where a signed-out visitor lands is state (`signedOutPath`) that the router's gates
 * read, so the redirect and the cleared account always arrive in the same render.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [account, setAccount] = useState<Account | null>(null);
  const [phase, setPhase] = useState<AuthState['phase']>('loading');
  const [bootError, setBootError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [signedOutPath, setSignedOutPath] = useState<string | null>(null);

  // One client for the app's lifetime; its 401 handler only uses stable values.
  const [client] = useState(
    () =>
      new ApiClient({
        onUnauthorized: () => {
          queryClient.clear();
          setAccount(null);
          setNotice(SESSION_ENDED);
          setSignedOutPath('/signin');
        },
      }),
  );

  const apply = useCallback((boot: Boot): Account | null => {
    if ('error' in boot) {
      setBootError(boot.error);
      // A failed re-check after boot keeps the current session state.
      setPhase((p) => (p === 'ready' ? p : 'error'));
      throw boot.error;
    }
    setAccount(boot.account);
    setPhase('ready');
    return boot.account;
  }, []);

  const refresh = useCallback(async () => apply(await readAccount(client)), [apply, client]);

  useEffect(() => {
    let live = true;
    void readAccount(client).then((boot) => {
      if (!live) return;
      try {
        apply(boot);
      } catch {
        // Shown by the boot error page.
      }
    });
    return () => {
      live = false;
    };
  }, [apply, client]);

  const start = useCallback(
    (next: Account) => {
      queryClient.clear();
      setNotice(null);
      setSignedOutPath(null);
      setAccount(next);
      return next;
    },
    [queryClient],
  );

  const signIn = useCallback(
    async (email: string, password: string) => start(await client.signIn(email, password)),
    [client, start],
  );

  const signUp = useCallback(
    async (email: string, password: string) => start(await client.signUp(email, password)),
    [client, start],
  );

  const clear = useCallback(
    (message?: string, landing = '/welcome') => {
      queryClient.clear();
      forgetSource();
      setAccount(null);
      setNotice(message ?? null);
      setSignedOutPath(landing);
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    await client.signOut();
    clear('You signed out.', '/signin');
  }, [client, clear]);

  const value = useMemo<AuthState>(
    () => ({ account, phase, bootError, notice, signedOutPath, client, signIn, signUp, signOut, refresh, clear }),
    [account, phase, bootError, notice, signedOutPath, client, signIn, signUp, signOut, refresh, clear],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
