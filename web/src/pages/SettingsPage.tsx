import { useQueryClient } from '@tanstack/react-query';
import { Download, LogOut, QrCode, RefreshCw, Trash2, Unplug, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError, errorMessage } from '../api/errors';
import { DEVICES_KEY, ME_KEY, useDevices, useMe, useMeStatus } from '../api/hooks';
import type { Device, MeInfo, MeStatus, PairingCode, ProfileInput, Sensitivity, Unit } from '../api/types';
import { useAccount, useApi, useAuth } from '../auth/context';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Field, FieldError, PasswordInput } from '../components/Field';
import { describedBy } from '../lib/aria';
import { PageHeader } from '../components/PageHeader';
import { ProfileForm, type ProfileValues } from '../components/ProfileForm';
import { ErrorState, Skeleton } from '../components/States';
import { ICON } from '../components/icon';
import { describeDevice } from '../lib/devices';
import { saveBlob } from '../lib/download';
import { quantileIndex, sortForecast } from '../lib/forecast';
import { fmtInt, fmtQuantile } from '../lib/format';
import { formatCountdown, secondsLeft } from '../lib/pairing';
import { forgetSource } from '../lib/source';
import { formatDateTime, formatWhen, tryParseApiTime } from '../lib/time';
import { UNITS, formatGlucose } from '../lib/units';

const SENSITIVITIES: { key: Sensitivity; label: string; q: [number, number]; text: string }[] = [
  {
    key: 'standard',
    label: 'Standard',
    q: [0.25, 0.75],
    text: 'Warns when the likely half of outcomes reaches a low or a high. The fewest warnings; some arrive later.',
  },
  {
    key: 'cautious',
    label: 'Cautious',
    q: [0.1, 0.9],
    text: 'Warns when 8 in 10 outcomes could reach a low or a high. Earlier warnings, and more of them.',
  },
  {
    key: 'very_cautious',
    label: 'Very cautious',
    q: [0.02, 0.98],
    text: 'Warns when almost any outcome, 96 in 100, could reach a low or a high. The earliest warnings, including many that will not happen.',
  },
];

/** Saves the full profile with one part changed; every section uses it. */
function useSaveProfile(me: MeInfo) {
  const api = useApi();
  const { refresh } = useAuth();
  const queryClient = useQueryClient();
  return async (patch: Partial<ProfileInput>) => {
    const p = me.profile;
    if (!p) throw new Error('Set up your profile first.');
    await api.saveProfile({
      age: p.age,
      gender: p.gender,
      bmi: p.bmi,
      diabetes_type: p.diabetes_type,
      sensitivity: p.sensitivity ?? 'standard',
      unit: me.unit,
      ...patch,
    });
    await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
    await refresh();
  };
}

function Saved({ text }: { text: string | null }) {
  return (
    <span role="status" className="saved">
      {text}
    </span>
  );
}

function ProfileSection({ me }: { me: MeInfo }) {
  const save = useSaveProfile(me);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  async function submit(v: ProfileValues) {
    setError(null);
    setSaved(null);
    try {
      await save({ age: v.age, gender: v.gender, bmi: v.bmi, diabetes_type: v.diabetes_type });
      setSaved('Saved. New forecasts use these details.');
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <section className="sheet-section settings-section" aria-labelledby="profile-heading">
      <div className="settings-head">
        <h2 id="profile-heading">About you</h2>
        <p className="muted">The four facts the model reads with your readings.</p>
      </div>
      <ProfileForm
        initial={me.profile}
        unit={me.unit}
        withUnits={false}
        submitLabel="Save changes"
        busyLabel="Saving"
        onSubmit={submit}
        error={error}
        footer={<Saved text={saved} />}
      />
    </section>
  );
}

/** Lowest lower edge and highest upper edge over the next hour of the latest forecast, per setting. */
function bandEdges(status: MeStatus | undefined, q: [number, number]): [number, number] | null {
  const p = status?.prediction;
  if (!p) return null;
  const f = sortForecast(p);
  const lo = quantileIndex(f.quantiles, q[0]);
  const hi = quantileIndex(f.quantiles, q[1]);
  if (lo < 0 || hi < 0) return null;
  const lows = f.values.map((row) => row[lo] ?? Number.NaN).filter(Number.isFinite);
  const highs = f.values.map((row) => row[hi] ?? Number.NaN).filter(Number.isFinite);
  if (!lows.length || !highs.length) return null;
  return [Math.min(...lows), Math.max(...highs)];
}

function SensitivitySection({ me }: { me: MeInfo }) {
  const save = useSaveProfile(me);
  const status = useMeStatus(true, me.readings.count > 0);
  const name = useId();
  const current = me.profile?.sensitivity ?? 'standard';
  const [choice, setChoice] = useState<Sensitivity>(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const t0 = tryParseApiTime(status.data?.prediction?.t0);
  const now = tryParseApiTime(status.data?.now);
  const unit = me.unit;
  const lowLine = formatGlucose(me.model.hypo_mg_dl, unit);
  const highLine = formatGlucose(me.model.hyper_mg_dl, unit);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await save({ sensitivity: choice });
      await status.refetch();
      setSaved('Saved. Today and new alerts use this setting.');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet-section settings-section" aria-labelledby="sensitivity-heading">
      <div className="settings-head">
        <h2 id="sensitivity-heading">Alert sensitivity</h2>
        <p className="muted">
          How wide a forecast band must reach below {lowLine} or above {highLine} {unit} before you are warned. A wider band
          warns earlier and more often.
        </p>
      </div>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <fieldset className="radio-cards">
          <legend className="visually-hidden">Alert sensitivity</legend>
          {SENSITIVITIES.map((s) => {
            const edges = bandEdges(status.data, s.q);
            return (
              <label key={s.key} className="radio-card">
                <input type="radio" name={name} value={s.key} checked={choice === s.key} onChange={() => setChoice(s.key)} />
                <span className="radio-card-body">
                  <span className="radio-card-title">
                    {s.label}
                    {current === s.key ? <span className="chip chip-clock">Current</span> : null}
                  </span>
                  <span className="radio-card-text">{s.text}</span>
                  {edges ? (
                    <span className="radio-card-preview num">
                      Your forecast{t0 !== null ? ` from ${formatWhen(t0, now)}` : ''}: {formatGlucose(edges[0], unit)} to{' '}
                      {formatGlucose(edges[1], unit)} {unit}
                    </span>
                  ) : null}
                  <span className="radio-card-meta num">
                    Band edges {fmtQuantile(s.q[0])} and {fmtQuantile(s.q[1])}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="form-actions">
          <button type="submit" className="button button-primary" disabled={busy || choice === current}>
            {busy ? 'Saving' : 'Save changes'}
          </button>
          <Saved text={saved} />
        </div>
      </form>
    </section>
  );
}

function UnitsSection({ me }: { me: MeInfo }) {
  const save = useSaveProfile(me);
  const name = useId();
  const [unit, setUnit] = useState<Unit>(me.unit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      await save({ unit });
      setSaved(`Saved. Values now show in ${unit}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet-section settings-section" aria-labelledby="units-heading">
      <div className="settings-head">
        <h2 id="units-heading">Units</h2>
        <p className="muted">Every value, chart and limit shows in this unit. 100 mg/dL is 5.6 mmol/L.</p>
      </div>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <fieldset className="field options-field">
          <legend>Glucose units</legend>
          <div className="options">
            {UNITS.map((u) => (
              <label key={u} className="option">
                <input type="radio" name={name} value={u} checked={unit === u} onChange={() => setUnit(u)} />
                <span>
                  {u} <span className="muted num">(target {u === 'mmol/L' ? '3.9–10.0' : '70–180'})</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="form-actions">
          <button type="submit" className="button button-primary" disabled={busy || unit === me.unit}>
            {busy ? 'Saving' : 'Save changes'}
          </button>
          <Saved text={saved} />
        </div>
      </form>
    </section>
  );
}

function DataSection({ me }: { me: MeInfo }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const count = me.readings.count;
  const first = tryParseApiTime(me.readings.first);
  const last = tryParseApiTime(me.readings.last);

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await api.exportReadings();
      saveBlob(blob, filename);
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  async function deleteReadings() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteReadings();
      forgetSource();
      await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
      setConfirm(false);
      navigate('/setup/data');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sheet-section settings-section" aria-labelledby="data-heading">
      <div className="settings-head">
        <h2 id="data-heading">Your data</h2>
        <p className="muted num">
          {count
            ? `${fmtInt(count)} ${count === 1 ? 'reading' : 'readings'}, from ${formatDateTime(first)} to ${formatDateTime(last)}.`
            : 'No readings yet.'}
        </p>
      </div>
      <div className="settings-actions">
        <div className="settings-action">
          <button type="button" className="button" disabled={exporting || count === 0} onClick={() => void exportCsv()}>
            <Download {...ICON} />
            {exporting ? 'Exporting' : 'Export readings'}
          </button>
          <p className="field-hint">A CSV of every reading, with times in your time zone.</p>
          {exportError ? <FieldError>{exportError}</FieldError> : null}
        </div>
        <div className="settings-action">
          <button type="button" className="button button-danger-quiet" disabled={count === 0} onClick={() => setConfirm(true)}>
            <Trash2 {...ICON} />
            Delete readings
          </button>
          <p className="field-hint">Keeps your account and settings.</p>
        </div>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete all your readings?"
        confirmLabel="Delete readings"
        busyLabel="Deleting readings"
        busy={busy}
        onConfirm={() => void deleteReadings()}
        onClose={() => setConfirm(false)}
      >
        <p>
          Delete {fmtInt(count)} {count === 1 ? 'reading' : 'readings'}, all forecasts and alerts. Your account and settings stay.
          This cannot be undone.
        </p>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </ConfirmDialog>
    </section>
  );
}

/** While open the devices list is polled this often, so a phone that pairs shows up. */
const PAIR_POLL_MS = 5_000;

interface PairingPanelProps {
  pairing: PairingCode | null;
  busy: boolean;
  error: string | null;
  onRenew: () => void;
  onClose: () => void;
}

/** The pairing QR and code with a live countdown; mounted only while open. */
function PairingPanel({ pairing, busy, error, onRenew, onClose }: PairingPanelProps) {
  const headingId = useId();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const left = pairing ? secondsLeft(pairing.expires_at, now) : 0;
  const expired = pairing !== null && left === 0;

  return (
    <div className="pair-panel" role="region" aria-labelledby={headingId}>
      <div className="pair-top">
        <h3 id={headingId}>Connect a phone</h3>
        <button type="button" className="button button-quiet" onClick={onClose}>
          <X {...ICON} />
          Close
        </button>
      </div>
      <p className="pair-steps">Open GlucoRAG on your phone and tap Scan QR code. Or point your phone&apos;s camera at the code.</p>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {pairing === null && busy ? <Skeleton label="Making a pairing code" rows={3} variant="block" /> : null}
      {pairing ? (
        <div className="pair-body">
          {/* The CSP allows data: images, and an <img> never runs script inside an SVG. */}
          <img
            className={expired ? 'pair-qr pair-qr-expired' : 'pair-qr'}
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(pairing.qr_svg)}`}
            alt={`QR code for pairing code ${pairing.code}`}
          />
          <dl className="pair-facts">
            <div>
              <dt>Pairing code</dt>
              <dd className="pair-code">{pairing.code}</dd>
              <dd className="pair-expiry num">{expired ? 'Expired' : `Expires in ${formatCountdown(left)}`}</dd>
            </div>
            <div>
              <dt>Server address</dt>
              <dd className="pair-server">
                <code>{pairing.server_url}</code>
              </dd>
              {pairing.server_url_guessed ? (
                <dd className="pair-note">If your phone can&apos;t reach this address, set GLUCORAG_PUBLIC_URL</dd>
              ) : null}
            </div>
          </dl>
        </div>
      ) : null}
      <p role="status" className="pair-status">
        {expired ? 'This code has expired. Make a new one.' : pairing ? 'Waiting for your phone. This list updates when it connects.' : null}
      </p>
      <div>
        <button type="button" className="button" disabled={busy} onClick={onRenew}>
          <RefreshCw {...ICON} />
          {busy ? 'Making a new code' : 'Make a new code'}
        </button>
      </div>
    </div>
  );
}

/** Phones signed in with a device token; the Add-data choices link here as `/settings#devices`. */
function DevicesSection() {
  const api = useApi();
  const queryClient = useQueryClient();
  const canPair = useAccount().role === 'person';
  // Device ids present when the pairing panel opened; null while it is closed.
  const [known, setKnown] = useState<ReadonlySet<number> | null>(null);
  const devices = useDevices(known ? PAIR_POLL_MS : false);
  const { hash } = useLocation();
  const ref = useRef<HTMLElement>(null);
  const [target, setTarget] = useState<Device | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [pairBusy, setPairBusy] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);
  const [connected, setConnected] = useState<string | null>(null);
  // Relative times are as of the fetch; the list refetches when the window regains focus.
  const now = devices.dataUpdatedAt;

  // A device that appeared while the panel is open is the phone that just paired: close the
  // panel once (adjusting state during render, so a later disconnect cannot reopen it).
  const added = known ? devices.data?.find((d) => !known.has(d.id)) : undefined;
  if (added) {
    setKnown(null);
    setPairing(null);
    setConnected(`Phone connected: ${added.device}.`);
  }

  useEffect(() => {
    if (hash === '#devices' && !devices.isPending) ref.current?.scrollIntoView({ block: 'start' });
  }, [hash, devices.isPending]);

  async function makeCode() {
    setPairBusy(true);
    setPairError(null);
    try {
      setPairing(await api.createPairing());
    } catch (err) {
      setPairError(errorMessage(err));
    } finally {
      setPairBusy(false);
    }
  }

  function openPairing() {
    setKnown(new Set((devices.data ?? []).map((d) => d.id)));
    setConnected(null);
    setPairing(null);
    void makeCode();
  }

  function closePairing() {
    setKnown(null);
    setPairing(null);
    setPairError(null);
  }

  async function disconnect(device: Device) {
    setBusy(true);
    setError(null);
    try {
      await api.revokeDevice(device.id);
      await queryClient.invalidateQueries({ queryKey: DEVICES_KEY });
      setTarget(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section ref={ref} id="devices" className="sheet-section settings-section" aria-labelledby="devices-heading">
      <div className="settings-head">
        <h2 id="devices-heading">Connected devices</h2>
        {devices.data?.length === 0 ? (
          <p className="muted">No phone connected. Install the GlucoRAG phone app to stream readings from Juggluco or xDrip+.</p>
        ) : null}
      </div>
      <div className="device-body">
        {devices.isPending ? <Skeleton label="Loading connected devices" rows={2} /> : null}
        {devices.isError ? (
          <ErrorState error={devices.error} title="Connected devices could not be loaded." onRetry={() => void devices.refetch()} />
        ) : null}
        {devices.data?.length ? (
          <ul className="device-list">
            {devices.data.map((d) => (
              <li key={d.id} className="device-row">
                <div className="device-text">
                  <p className="device-name">{d.device}</p>
                  <p className="device-meta num">{describeDevice(d, now)}</p>
                </div>
                <button
                  type="button"
                  className="button button-danger-quiet"
                  aria-label={`Disconnect ${d.device}`}
                  onClick={() => {
                    setError(null);
                    setTarget(d);
                  }}
                >
                  <Unplug {...ICON} />
                  Disconnect
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <Saved text={connected} />
        {canPair && known ? (
          <PairingPanel pairing={pairing} busy={pairBusy} error={pairError} onRenew={() => void makeCode()} onClose={closePairing} />
        ) : null}
        {canPair && !known ? (
          <div>
            <button type="button" className="button button-primary" disabled={!devices.data} onClick={openPairing}>
              <QrCode {...ICON} />
              Connect a phone
            </button>
          </div>
        ) : null}
      </div>
      <ConfirmDialog
        open={target !== null}
        title={`Disconnect ${target?.device ?? ''}?`}
        confirmLabel="Disconnect"
        busyLabel="Disconnecting"
        busy={busy}
        onConfirm={() => {
          if (target) void disconnect(target);
        }}
        onClose={() => setTarget(null)}
      >
        <p>It stops uploading readings until you sign in on it again.</p>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
      </ConfirmDialog>
    </section>
  );
}

function PasswordForm() {
  const api = useApi();
  const id = useId();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [errors, setErrors] = useState<{ current?: string; next?: string; form?: string }>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(null);
    const errs = {
      current: current ? undefined : 'Enter your current password.',
      next: next.length >= 10 ? undefined : 'Use at least 10 characters.',
    };
    setErrors(errs);
    if (errs.current || errs.next) return;
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setSaved('Password changed. Other devices are signed out.');
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setErrors({ current: 'This is not your current password.' });
      else if (err instanceof ApiError && err.status === 422) setErrors({ next: err.message });
      else setErrors({ form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form password-form" onSubmit={(e) => void submit(e)} noValidate>
      <h3>Change password</h3>
      <Field id={`${id}-current`} label="Current password" error={errors.current}>
        <PasswordInput
          id={`${id}-current`}
          name="current-password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          aria-invalid={errors.current ? true : undefined}
          aria-describedby={describedBy(`${id}-current`, false, Boolean(errors.current))}
        />
      </Field>
      <Field id={`${id}-new`} label="New password" hint="At least 10 characters." error={errors.next}>
        <PasswordInput
          id={`${id}-new`}
          name="new-password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          aria-invalid={errors.next ? true : undefined}
          aria-describedby={describedBy(`${id}-new`, true, Boolean(errors.next))}
        />
      </Field>
      {errors.form ? (
        <p className="form-error" role="alert">
          {errors.form}
        </p>
      ) : null}
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {busy ? 'Changing password' : 'Change password'}
        </button>
        <Saved text={saved} />
      </div>
    </form>
  );
}

function AccountSection({ me }: { me: MeInfo | null }) {
  const api = useApi();
  const account = useAccount();
  const { signOut, clear } = useAuth();
  const id = useId();
  const [confirm, setConfirm] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const person = account.role === 'person';
  const count = me?.readings.count ?? 0;

  async function deleteAccount() {
    if (!password) {
      setError('Enter your password to confirm.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password);
      // The router's gate moves the signed-out page to Welcome.
      clear('Your account and all its data were deleted.', '/welcome');
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? 'This password is not correct.' : errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <section className="sheet-section settings-section" aria-labelledby="account-heading">
      <div className="settings-head">
        <h2 id="account-heading">Account</h2>
        <p className="muted">
          Signed in as <strong className="account-email">{account.email}</strong>
          {person ? '' : ', a clinician account'}.
        </p>
      </div>
      <div className="account-grid">
        <PasswordForm />
        <div className="account-side">
          <div className="settings-action">
            <button
              type="button"
              className="button"
              onClick={() => {
                setSignOutError(null);
                signOut().catch((err: unknown) => setSignOutError(errorMessage(err)));
              }}
            >
              <LogOut {...ICON} />
              Sign out
            </button>
            {signOutError ? <FieldError>{signOutError}</FieldError> : null}
          </div>
          {person ? (
            <div className="settings-action">
              <button type="button" className="button button-danger-quiet" onClick={() => setConfirm(true)}>
                <Trash2 {...ICON} />
                Delete account
              </button>
              <p className="field-hint">Deletes the account and everything in it.</p>
            </div>
          ) : null}
        </div>
      </div>
      {person ? (
        <ConfirmDialog
          open={confirm}
          title="Delete your account?"
          confirmLabel="Delete account"
          busyLabel="Deleting account"
          busy={busy}
          onConfirm={() => void deleteAccount()}
          onClose={() => {
            setConfirm(false);
            setPassword('');
            setError(null);
          }}
        >
          <p>
            Delete your account, {fmtInt(count)} {count === 1 ? 'reading' : 'readings'}, all forecasts and alerts, and your settings.
            This cannot be undone. Export your readings first if you want a copy.
          </p>
          <Field id={`${id}-confirm-password`} label="Your password" error={error}>
            <PasswordInput
              id={`${id}-confirm-password`}
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={describedBy(`${id}-confirm-password`, false, Boolean(error))}
            />
          </Field>
        </ConfirmDialog>
      ) : null}
    </section>
  );
}

export function SettingsPage() {
  const account = useAccount();
  const person = account.role === 'person';
  const me = useMe(person);
  const sections = person && me.data?.profile ? me.data : null;

  return (
    <>
      <PageHeader title="Settings" />
      <div className="sheet">
        {person && me.isPending ? (
          <section className="sheet-section">
            <Skeleton label="Loading your settings" rows={6} />
          </section>
        ) : null}
        {person && me.isError ? (
          <section className="sheet-section">
            <ErrorState error={me.error} title="Your settings could not be loaded." onRetry={() => void me.refetch()} />
          </section>
        ) : null}
        {person && me.data && !me.data.profile ? (
          <section className="sheet-section prose-block">
            <h2>Set up your profile</h2>
            <p>
              Forecasts need four facts about you. <Link to="/setup">Set up your profile</Link> here, or connect your phone below and
              set it up in the app.
            </p>
          </section>
        ) : null}
        {sections ? (
          <>
            <ProfileSection me={sections} />
            <SensitivitySection me={sections} />
            <UnitsSection me={sections} />
            <DataSection me={sections} />
          </>
        ) : null}
        {me.data || !person ? <DevicesSection /> : null}
        {!person || me.data ? <AccountSection me={me.data ?? null} /> : null}
      </div>
    </>
  );
}
