import { useQueryClient } from '@tanstack/react-query';
import { FileUp } from 'lucide-react';
import { useId, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError, errorMessage } from '../api/errors';
import { ME_KEY, useMe } from '../api/hooks';
import type { CycleResult, ImportDates, ImportResult, ImportUnit, MeInfo, RejectedReading, Unit } from '../api/types';
import { useAccount, useApi } from '../auth/context';
import { Field, FieldError } from '../components/Field';
import { PageHeader } from '../components/PageHeader';
import { ErrorState, Skeleton } from '../components/States';
import { ICON } from '../components/icon';
import { describedBy } from '../lib/aria';
import { fmtInt } from '../lib/format';
import { rememberSource } from '../lib/source';
import { formatDateTime, formatWhen, epochToWall, tryParseApiTime } from '../lib/time';
import { detectTimeZone, timeZoneOptions } from '../lib/timezone';
import { UNITS, formatGlucoseUnit, parseGlucose } from '../lib/units';

const MAX_BYTES = 10 * 1024 * 1024;

type Tab = 'reading' | 'import';
const TABS: { key: Tab; label: string }[] = [
  { key: 'reading', label: 'Enter a reading' },
  { key: 'import', label: 'Import a file' },
];

/** `YYYY-MM-DDTHH:MM` in the browser's local time, for a datetime-local input. */
function localInputValue(epochMs: number): string {
  const d = new Date(epochMs);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// ---------- Enter a reading ----------

interface ReadingErrors {
  value?: string;
  time?: string;
  form?: string;
}

/** A refused reading as a field-level message, from the service's reason. */
function rejection(r: RejectedReading, me: MeInfo | undefined): ReadingErrors {
  const latest = tryParseApiTime(me?.readings.last ?? null);
  switch (r.reason) {
    case 'duplicate':
      return { time: 'You already have a reading at this time. Change the time to add another one.' };
    case 'out_of_order':
      return {
        time: `New readings must be later than your latest one${latest !== null ? `, ${formatDateTime(latest)}` : ''}. To add older readings, import a file.`,
      };
    case 'future':
      return { time: 'This time is in the future. Use the current time or earlier.' };
    case 'non_finite':
    case 'non_positive':
      return { value: 'Enter a glucose value above zero, like 6.2 or 112.' };
    default:
      return { form: r.detail ? `The reading was refused: ${r.detail}` : 'The reading was refused.' };
  }
}

function outcomeLine(r: CycleResult): string {
  if (r.status === 'predicted') return 'Your forecast is updated.';
  if (r.status === 'warming_up') return 'Forecasts start once there are 2 hours of readings.';
  if (r.status === 'data_gap') return 'There is a gap of more than an hour before it, so forecasts restart after 2 hours of readings.';
  return '';
}

function ReadingForm({ me }: { me: MeInfo }) {
  const api = useApi();
  const account = useAccount();
  const queryClient = useQueryClient();
  const id = useId();
  const valueRef = useRef<HTMLInputElement>(null);
  const timeRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState<Unit>(me.unit);
  const [time, setTime] = useState(() => localInputValue(Date.now()));
  // Latest time the picker offers; the service checks for future times itself.
  const [maxTime] = useState(() => localInputValue(Date.now() + 24 * 3_600_000));
  const [errors, setErrors] = useState<ReadingErrors>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ text: string; outcome: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setDone(null);
    const mg = parseGlucose(value, unit);
    const when = time ? new Date(time) : null;
    const next: ReadingErrors = {
      value: mg === null ? `Enter a glucose value in ${unit}, like ${unit === 'mmol/L' ? '6.2' : '112'}.` : undefined,
      time: when === null || Number.isNaN(when.getTime()) ? 'Enter the date and time of the reading.' : undefined,
    };
    setErrors(next);
    if (next.value || next.time || !when) {
      (next.value ? valueRef : timeRef).current?.focus();
      return;
    }
    setBusy(true);
    try {
      const result = await api.addReading({
        timestamp: when.toISOString(),
        glucose: Number(value.trim().replace(',', '.')),
        unit,
      });
      rememberSource(account.email, 'manual', result.timestamp);
      await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
      const at = tryParseApiTime(result.timestamp);
      setDone({
        text: `Added ${formatGlucoseUnit(mg, unit)} at ${formatWhen(at, epochToWall(Date.now()))}.`,
        outcome: outcomeLine(result),
      });
      setValue('');
      setTime(localInputValue(Date.now()));
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.detail && typeof err.detail === 'object' && 'reason' in err.detail) {
        const r = rejection(err.detail as RejectedReading, me);
        setErrors(r);
        if (r.value) valueRef.current?.focus();
        else if (r.time) timeRef.current?.focus();
      } else {
        setErrors({ form: errorMessage(err) });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form reading-form" onSubmit={(e) => void submit(e)} noValidate>
      <div className="form-row">
        <Field id={`${id}-value`} label="Glucose" error={errors.value}>
          <input
            ref={valueRef}
            id={`${id}-value`}
            name="glucose"
            className="input-short input-value num"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            placeholder={unit === 'mmol/L' ? '6.2' : '112'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={errors.value ? true : undefined}
            aria-describedby={describedBy(`${id}-value`, false, Boolean(errors.value))}
          />
        </Field>
        <Field id={`${id}-unit`} label="Unit">
          <select id={`${id}-unit`} name="unit" value={unit} onChange={(e) => setUnit(e.target.value as Unit)}>
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field id={`${id}-time`} label="Time" hint="Defaults to now, in your time zone." error={errors.time}>
        <input
          ref={timeRef}
          id={`${id}-time`}
          name="time"
          className="input-time"
          type="datetime-local"
          max={maxTime}
          value={time}
          onChange={(e) => setTime(e.target.value)}
          aria-invalid={errors.time ? true : undefined}
          aria-describedby={describedBy(`${id}-time`, true, Boolean(errors.time))}
        />
      </Field>
      {errors.form ? (
        <p className="form-error" role="alert">
          {errors.form}
        </p>
      ) : null}
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? 'Adding reading' : 'Add reading'}
        </button>
      </div>
      <div role="status" className="form-done-wrap">
        {done ? (
          <p className="form-done">
            {done.text} {done.outcome} <Link to="/">See Today</Link>
          </p>
        ) : null}
      </div>
    </form>
  );
}

// ---------- Import a file ----------

const FORMAT_NAME: Record<string, string> = {
  libreview: 'FreeStyle LibreView export',
  dexcom: 'Dexcom Clarity export',
  generic: 'CSV with a time and a glucose column',
};

const REJECT_NAME: Record<string, string> = {
  rejected_duplicate: 'two rows at the same time',
  rejected_out_of_order: 'out of time order',
  rejected_future: 'times in the future',
  rejected_non_finite: 'not a number',
  rejected_non_positive: 'zero or below',
};

function ImportSummary({ r }: { r: ImportResult }) {
  const rejected = Object.entries(r.outcomes).filter(([k]) => k.startsWith('rejected'));
  const rejectedTotal = rejected.reduce((n, [, v]) => n + v, 0);
  const forecasts = r.outcomes.predicted ?? 0;
  const rows: { label: string; n: number; why: string }[] = [
    { label: 'Added', n: r.accepted, why: 'new readings saved to your account' },
    { label: 'Already present', n: r.already_present, why: 'a reading at that exact time is already saved, so skipped' },
    { label: `Older than ${r.window_days} days`, n: r.older_than_window, why: `more than ${r.window_days} days before the file's last reading, so skipped` },
    { label: 'Unusable rows', n: r.unusable_rows, why: 'missing a time or a glucose value' },
    {
      label: 'Refused',
      n: rejectedTotal,
      why: rejected.length ? rejected.map(([k, v]) => `${fmtInt(v)} ${REJECT_NAME[k] ?? k.replace(/^rejected_/, '').replace(/_/g, ' ')}`).join(', ') : 'none refused by the checks',
    },
  ];
  return (
    <section className="import-result" aria-labelledby="import-result-title">
      <h3 id="import-result-title">{r.accepted ? `Imported ${fmtInt(r.accepted)} readings` : 'No new readings added'}</h3>
      <p>
        {FORMAT_NAME[r.format] ?? r.format}, values in {r.unit}. The file runs from {formatDateTime(tryParseApiTime(r.first))} to{' '}
        {formatDateTime(tryParseApiTime(r.last))}.
      </p>
      {r.date_ambiguous ? (
        <p className="import-note">
          Dates in this file could be read day first or month first. They were read{' '}
          {r.date_order === 'dmy' ? 'day first' : 'month first'}, which ends nearest to today. If that is wrong, delete
          these readings in Settings, then import again with Date order set to{' '}
          {r.date_order === 'dmy' ? 'Month first' : 'Day first'}.
        </p>
      ) : null}
      <dl className="count-list">
        <div className="count-total">
          <dt>Rows read</dt>
          <dd>
            <span className="num">{fmtInt(r.rows_read)}</span>
            <span className="count-why">every data row in the file</span>
          </dd>
        </div>
        {rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>
              <span className="num">{fmtInt(row.n)}</span>
              <span className="count-why">{row.why}</span>
            </dd>
          </div>
        ))}
      </dl>
      {r.accepted ? (
        <p className="import-next">
          {forecasts ? `${fmtInt(forecasts)} of the new readings produced a forecast. ` : 'No forecast yet: forecasts need 2 hours of recent readings. '}
          <Link className="button button-primary" to="/">
            See Today
          </Link>
        </p>
      ) : null}
    </section>
  );
}

function ImportForm() {
  const api = useApi();
  const account = useAccount();
  const queryClient = useQueryClient();
  const id = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const helpRef = useRef<HTMLDetailsElement>(null);
  const [detected] = useState(() => detectTimeZone());
  const [zones] = useState(() => timeZoneOptions(detected));
  const [tz, setTz] = useState(detected);
  const [unit, setUnit] = useState<ImportUnit>('auto');
  const [dates, setDates] = useState<ImportDates>('auto');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formatError, setFormatError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  function choose(f: File | null | undefined) {
    setResult(null);
    setFormatError(false);
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setFile(null);
      setError('This file is larger than 10 MB. Export a shorter date range and try again.');
      return;
    }
    setError(null);
    setFile(f);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files[0]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError('Choose a CSV file first.');
      fileRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setFormatError(false);
    setResult(null);
    try {
      const r = await api.importFile(await file.text(), tz.trim() || detected, unit, dates);
      setResult(r);
      if (r.accepted) rememberSource(account.email, 'import', r.last);
      await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
    } catch (err) {
      setError(errorMessage(err));
      setFormatError(err instanceof ApiError && err.status === 422);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form import-form" onSubmit={(e) => void submit(e)} noValidate>
      <div
        className={`dropzone${dragging ? ' is-dragging' : ''}${file ? ' has-file' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <FileUp {...ICON} className="dropzone-icon" />
        {file ? (
          <p className="dropzone-file">
            <span className="dropzone-name">{file.name}</span> <span className="muted num">{fmtInt(Math.max(1, file.size / 1024))} KB</span>
          </p>
        ) : (
          <p>Drop your CSV export here, or</p>
        )}
        <label className="button file-button">
          <input
            ref={fileRef}
            className="visually-hidden"
            type="file"
            name="file"
            accept=".csv,.txt,text/csv,text/plain"
            onChange={(e) => choose(e.target.files?.[0])}
          />
          {file ? 'Choose another file' : 'Choose a file'}
        </label>
      </div>

      <div className="form-row">
        <Field
          id={`${id}-tz`}
          label="Time zone of the file"
          hint={`Exports list times without a zone. Detected from this browser: ${detected}.`}
        >
          {zones.length ? (
            <select id={`${id}-tz`} name="tz" value={tz} onChange={(e) => setTz(e.target.value)} aria-describedby={`${id}-tz-hint`}>
              {zones.map((z) => (
                <option key={z} value={z}>
                  {z.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          ) : (
            <input id={`${id}-tz`} name="tz" type="text" value={tz} onChange={(e) => setTz(e.target.value)} aria-describedby={`${id}-tz-hint`} />
          )}
        </Field>
        <Field id={`${id}-unit`} label="Unit in the file" hint="Auto-detect reads it from the column name.">
          <select id={`${id}-unit`} name="unit" value={unit} onChange={(e) => setUnit(e.target.value as ImportUnit)} aria-describedby={`${id}-unit-hint`}>
            <option value="auto">Auto-detect</option>
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id={`${id}-dates`}
          label="Date order"
          hint="For dates like 06-10-2026. Auto-detect picks the order that fits the file."
        >
          <select
            id={`${id}-dates`}
            name="dates"
            value={dates}
            onChange={(e) => setDates(e.target.value as ImportDates)}
            aria-describedby={`${id}-dates-hint`}
          >
            <option value="auto">Auto-detect</option>
            <option value="dmy">Day first (06-10 is 6 Oct)</option>
            <option value="mdy">Month first (06-10 is 10 Jun)</option>
          </select>
        </Field>
      </div>

      <details ref={helpRef} id="format-help" className="disclosure-section format-help">
        <summary>Which files work?</summary>
        <div className="format-help-body">
          <h3>FreeStyle Libre</h3>
          <p>
            In LibreView, open Glucose History and choose Download glucose data. The file has a line about the export, then a
            header with Device Timestamp and Historic Glucose. Historic readings (every 15 minutes) are used.
          </p>
          <h3>Dexcom</h3>
          <p>In Dexcom Clarity, choose Export, then save the CSV. Rows of type EGV are used.</p>
          <h3>Any other CSV</h3>
          <p>
            A header row with a time column (for example <code>timestamp</code>) and a glucose column (for example{' '}
            <code>glucose</code>). Times like 2026-10-06 14:30 or 06-10-2026 14:30 both work.
          </p>
          <p>Files up to 10 MB. Readings far older than the file&rsquo;s last one are skipped, and the result says how many.</p>
        </div>
      </details>

      {error ? (
        <div className="form-error-block" role="alert">
          <FieldError>{error}</FieldError>
          {formatError ? (
            <p>
              <a
                href="#format-help"
                onClick={(e) => {
                  e.preventDefault();
                  if (helpRef.current) {
                    helpRef.current.open = true;
                    helpRef.current.querySelector('summary')?.focus();
                  }
                }}
              >
                See which files work
              </a>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? 'Importing' : 'Import file'}
        </button>
      </div>
      <div role="status">{result ? <ImportSummary r={result} /> : null}</div>
    </form>
  );
}

// ---------- Page ----------

export function AddDataPage() {
  const me = useMe();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('tab') === 'import' ? 'import' : 'reading';
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ reading: null, import: null });
  const id = useId();

  function select(next: Tab) {
    setParams(next === 'import' ? { tab: 'import' } : {}, { replace: true });
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const i = TABS.findIndex((t) => t.key === tab);
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length;
    const next = TABS[j]?.key ?? tab;
    select(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <>
      <PageHeader title="Add data" />
      <div className="sheet">
        <div className="tabs" role="tablist" aria-label="How to add data" onKeyDown={onKey}>
          {TABS.map((t) => (
            <button
              key={t.key}
              ref={(el) => {
                tabRefs.current[t.key] = el;
              }}
              type="button"
              role="tab"
              id={`${id}-tab-${t.key}`}
              aria-selected={tab === t.key}
              aria-controls={`${id}-panel-${t.key}`}
              tabIndex={tab === t.key ? 0 : -1}
              className="tab"
              onClick={() => select(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="sheet-section tab-panel" role="tabpanel" id={`${id}-panel-${tab}`} aria-labelledby={`${id}-tab-${tab}`}>
          {me.isError ? <ErrorState error={me.error} title="Your account could not be loaded." onRetry={() => void me.refetch()} /> : null}
          {me.isPending ? <Skeleton label="Loading" rows={4} /> : null}
          {me.data ? tab === 'import' ? <ImportForm /> : <ReadingForm me={me.data} /> : null}
        </div>
      </div>
    </>
  );
}
