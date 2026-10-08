import type { UseQueryResult } from '@tanstack/react-query';
import { useState } from 'react';
import { errorMessage } from '../api/errors';
import { useDevices } from '../api/hooks';
import type { Device, PairingCode } from '../api/types';
import { useApi } from '../auth/context';

/** While the panel is open the devices list is polled this often, so a phone that pairs shows up. */
const PAIR_POLL_MS = 5_000;

export interface PhonePairing {
  /** The signed-in person's phones, polled while the panel is open. */
  devices: UseQueryResult<Device[]>;
  open: boolean;
  pairing: PairingCode | null;
  busy: boolean;
  error: string | null;
  /** "Phone connected: Pixel 8." once a phone pairs, until the panel opens again. */
  connected: string | null;
  /** Opens the panel with a fresh code; needs `devices.data`, so disable the button until it is there. */
  start: () => void;
  renew: () => void;
  close: () => void;
}

/**
 * Pairing state for one "Connect a phone" place (Settings, set-up, Add data). A device that
 * appears while the panel is open is the phone that just paired: the panel closes and
 * `connected` names it.
 */
export function usePhonePairing(): PhonePairing {
  const api = useApi();
  // Device ids present when the pairing panel opened; null while it is closed.
  const [known, setKnown] = useState<ReadonlySet<number> | null>(null);
  const devices = useDevices(known ? PAIR_POLL_MS : false);
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState<string | null>(null);

  // Adjusting state during render, so a later disconnect cannot reopen the panel.
  const added = known ? devices.data?.find((d) => !known.has(d.id)) : undefined;
  if (added) {
    setKnown(null);
    setPairing(null);
    setConnected(`Phone connected: ${added.device}.`);
  }

  async function makeCode() {
    setBusy(true);
    setError(null);
    try {
      setPairing(await api.createPairing());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return {
    devices,
    open: known !== null,
    pairing,
    busy,
    error,
    connected,
    start() {
      setKnown(new Set((devices.data ?? []).map((d) => d.id)));
      setConnected(null);
      setPairing(null);
      void makeCode();
    },
    renew() {
      void makeCode();
    },
    close() {
      setKnown(null);
      setPairing(null);
      setError(null);
    },
  };
}
