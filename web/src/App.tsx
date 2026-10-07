import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { ApiError } from './api/errors';
import { AuthProvider } from './auth/AuthProvider';
import { useAuth } from './auth/context';
import { ResearchNotice, Wordmark } from './components/Brand';
import { Layout } from './components/Layout';
import { ErrorState } from './components/States';
import { decide, type Area } from './lib/access';
import { AddDataPage } from './pages/AddDataPage';
import { AlertsPage } from './pages/AlertsPage';
import { ForbiddenPage } from './pages/ForbiddenPage';
import { HistoryPage } from './pages/HistoryPage';
import { ModelPage } from './pages/ModelPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PatientPage } from './pages/PatientPage';
import { SettingsPage } from './pages/SettingsPage';
import { SetupDataPage, SetupProfilePage } from './pages/SetupPages';
import { SignInPage, SignUpPage } from './pages/AuthPages';
import { SystemPage } from './pages/SystemPage';
import { TodayPage } from './pages/TodayPage';
import { WardPage } from './pages/WardPage';
import { WelcomePage } from './pages/WelcomePage';

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 401/403/404/409 are answers, not transient failures.
        retry: (count, err) => !(err instanceof ApiError && [401, 403, 404, 409].includes(err.status)) && count < 2,
        refetchOnWindowFocus: true,
        staleTime: 5_000,
      },
    },
  });
}

/** Applies the access decision for one route group; see `lib/access.ts`. */
function Gate({ area }: { area: Area }) {
  const { account, phase, bootError, refresh, signedOutPath } = useAuth();
  if (phase === 'loading') {
    return (
      <div className="boot" role="status">
        <span className="visually-hidden">Loading GlucoRAG</span>
      </div>
    );
  }
  if (phase === 'error') {
    return (
      <div className="auth-page">
        <main className="auth-sheet">
          <Wordmark large />
          <ErrorState error={bootError} title="GlucoRAG could not start." onRetry={() => void refresh().catch(() => undefined)} />
        </main>
        <ResearchNotice className="auth-notice" />
      </div>
    );
  }
  const decision = decide(area, account ? { role: account.role, hasProfile: account.has_profile } : null);
  if (decision.kind === 'redirect') return <Navigate to={account ? decision.to : (signedOutPath ?? decision.to)} replace />;
  if (decision.kind === 'forbidden') return <ForbiddenPage />;
  return <Outlet />;
}

export function App() {
  const [queryClient] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/ui" future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <Routes>
            <Route element={<Gate area="public" />}>
              <Route path="welcome" element={<WelcomePage />} />
              <Route path="signup" element={<SignUpPage />} />
              <Route path="signin" element={<SignInPage />} />
            </Route>
            <Route element={<Gate area="setup" />}>
              <Route path="setup" element={<SetupProfilePage />} />
            </Route>
            <Route element={<Gate area="setup-data" />}>
              <Route path="setup/data" element={<SetupDataPage />} />
            </Route>
            <Route element={<Gate area="shared" />}>
              <Route element={<Layout />}>
                <Route element={<Gate area="person" />}>
                  <Route index element={<TodayPage />} />
                  <Route path="history" element={<HistoryPage />} />
                  <Route path="add" element={<AddDataPage />} />
                </Route>
                <Route path="settings" element={<SettingsPage />} />
                <Route element={<Gate area="staff" />}>
                  <Route path="ward" element={<WardPage />} />
                  <Route path="patients/:id" element={<PatientPage />} />
                  <Route path="alerts" element={<AlertsPage />} />
                  <Route path="model" element={<ModelPage />} />
                  <Route path="system" element={<SystemPage />} />
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
