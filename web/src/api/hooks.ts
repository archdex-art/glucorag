import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useApi } from '../auth/context';
import type { AlertQuery } from './types';

/** Staff pages refresh every 15 s. */
export const REFRESH_MS = 15_000;
/** A person's pages refresh every 30 s; react-query skips the interval while the tab is hidden. */
export const PERSON_REFRESH_MS = 30_000;

export function useHealth(paused = false) {
  const api = useApi();
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

export function useCohort(paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: ['cohort'],
    queryFn: ({ signal }) => api.cohort(signal),
    enabled,
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

export function useStats(paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: ['stats'],
    queryFn: ({ signal }) => api.stats(signal),
    enabled,
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

/** `enabled: false` skips the request when the cohort already shows there is no forecast. */
export function useForecast(patientId: string, paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: ['forecast', patientId],
    queryFn: ({ signal }) => api.forecast(patientId, signal),
    enabled,
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

export function useHistory(patientId: string, since: string | null, paused = false) {
  const api = useApi();
  return useQuery({
    queryKey: ['history', patientId, since],
    queryFn: ({ signal }) => api.history(patientId, { since: since ?? undefined, limit: 10_000 }, signal),
    enabled: since !== null,
    placeholderData: keepPreviousData,
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

export function useAlerts(query: AlertQuery, paused = false) {
  const api = useApi();
  return useQuery({
    queryKey: ['alerts', query],
    queryFn: ({ signal }) => api.alerts(query, signal),
    placeholderData: keepPreviousData,
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

export function useModel() {
  const api = useApi();
  return useQuery({
    queryKey: ['model'],
    queryFn: ({ signal }) => api.model(signal),
    staleTime: 5 * 60_000,
  });
}

/** Live accuracy moves with each matched reading; refreshed like the other staff pages. */
export function useModelAccuracy(paused = false) {
  const api = useApi();
  return useQuery({
    queryKey: ['model', 'accuracy'],
    queryFn: ({ signal }) => api.modelAccuracy(signal),
    refetchInterval: paused ? false : REFRESH_MS,
  });
}

/** Public: which app files this server offers. */
export function useDownloads() {
  const api = useApi();
  return useQuery({
    queryKey: ['downloads'],
    queryFn: ({ signal }) => api.downloads(signal),
    staleTime: 5 * 60_000,
  });
}

// ---------- A person's own data ----------

/** Every query under this key belongs to the signed-in person; invalidate it after any write. */
export const ME_KEY = 'me';

export function useMe(enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: [ME_KEY, 'info'],
    queryFn: ({ signal }) => api.me(signal),
    enabled,
  });
}

export function useMeStatus(paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: [ME_KEY, 'status'],
    queryFn: ({ signal }) => api.status(signal),
    enabled,
    refetchInterval: paused ? false : PERSON_REFRESH_MS,
  });
}

export function useMeHistory(hours: number, paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: [ME_KEY, 'history', hours],
    queryFn: ({ signal }) => api.myHistory(hours, signal),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: paused ? false : PERSON_REFRESH_MS,
  });
}

export function useMeAlerts(limit: number, paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: [ME_KEY, 'alerts', limit],
    queryFn: ({ signal }) => api.myAlerts(limit, signal),
    enabled,
    refetchInterval: paused ? false : PERSON_REFRESH_MS,
  });
}

export function useMeAccuracy(paused = false, enabled = true) {
  const api = useApi();
  return useQuery({
    queryKey: [ME_KEY, 'accuracy'],
    queryFn: ({ signal }) => api.myAccuracy(signal),
    enabled,
    // A day's worth of forecasts barely moves it: refresh far less often than the status.
    refetchInterval: paused ? false : 5 * 60_000,
    retry: false,
  });
}

export const DEVICES_KEY = [ME_KEY, 'devices'] as const;

/** `pollMs` refetches on an interval, e.g. while waiting for a phone to pair. */
export function useDevices(pollMs: number | false = false) {
  const api = useApi();
  return useQuery({
    queryKey: DEVICES_KEY,
    queryFn: ({ signal }) => api.devices(signal),
    refetchInterval: pollMs,
  });
}
