import { useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import type { DiabetesType, Profile, Sex, Unit } from '../api/types';
import { BMI_MAX, BMI_MIN, bmiImperial, bmiInRange, bmiMetric, defaultMeasureSystem } from '../lib/bmi';
import { fmtNumber } from '../lib/format';
import { UNITS } from '../lib/units';
import { describedBy } from '../lib/aria';
import { Field, FieldError } from './Field';

export interface ProfileValues {
  diabetes_type: DiabetesType;
  age: number;
  gender: Sex;
  bmi: number;
  unit: Unit;
}

interface Props {
  initial: Profile | null;
  unit: Unit;
  /** Show the units question (set-up); Settings has its own units section. */
  withUnits: boolean;
  submitLabel: string;
  busyLabel: string;
  onSubmit: (values: ProfileValues) => Promise<void>;
  /** A server error to show under the form. */
  error?: string | null;
  /** Below the submit button, e.g. a saved confirmation. */
  footer?: ReactNode;
}

type BmiMode = 'bmi' | 'measure';
type System = 'metric' | 'imperial';

interface Errors {
  diabetes_type?: string;
  age?: string;
  gender?: string;
  bmi?: string;
}

/** Number from a text field; NaN when empty or not a number. */
const num = (s: string) => (s.trim() === '' ? Number.NaN : Number(s.replace(',', '.')));

interface OptionsProps<T extends string> {
  name: string;
  legend: string;
  hint: string;
  value: T | null;
  options: readonly { value: T; label: string }[];
  onChange: (v: T) => void;
  error?: string;
}

/** A labelled group of radio buttons with the reason the forecast needs it. */
function Options<T extends string>({ name, legend, hint, value, options, onChange, error }: OptionsProps<T>) {
  const id = useId();
  return (
    <fieldset className="field options-field" aria-describedby={describedBy(id, true, Boolean(error))}>
      <legend>{legend}</legend>
      <div className="options">
        {options.map((o) => (
          <label key={o.value} className="option">
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              aria-invalid={error ? true : undefined}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
      <p id={`${id}-hint`} className="field-hint">
        {hint}
      </p>
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </fieldset>
  );
}

/** About you: the four facts the model reads, with the reason for each. Shared by set-up and Settings. */
export function ProfileForm({ initial, unit: initialUnit, withUnits, submitLabel, busyLabel, onSubmit, error, footer }: Props) {
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const [type, setType] = useState<DiabetesType | null>(initial?.diabetes_type ?? null);
  const [age, setAge] = useState(initial ? String(initial.age) : '');
  const [sex, setSex] = useState<Sex | null>(initial?.gender ?? null);
  // New profiles work BMI out from height and weight; a saved BMI stays editable as a number.
  const [mode, setMode] = useState<BmiMode>(initial ? 'bmi' : 'measure');
  const [bmiText, setBmiText] = useState(initial ? String(initial.bmi) : '');
  const [system, setSystem] = useState<System>(() =>
    defaultMeasureSystem(typeof navigator === 'undefined' ? undefined : navigator.language),
  );
  const [cm, setCm] = useState('');
  const [kg, setKg] = useState('');
  const [ft, setFt] = useState('');
  const [inch, setInch] = useState('');
  const [lb, setLb] = useState('');
  const [unit, setUnit] = useState<Unit>(initialUnit);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  const computed =
    mode === 'measure'
      ? system === 'metric'
        ? bmiMetric(num(cm), num(kg))
        : bmiImperial(num(ft), num(inch), num(lb))
      : null;
  const bmi = mode === 'bmi' ? (Number.isFinite(num(bmiText)) ? num(bmiText) : null) : computed;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ageN = num(age);
    const next: Errors = {
      diabetes_type: type ? undefined : 'Choose type 1 or type 2.',
      age: Number.isInteger(ageN) && ageN >= 1 && ageN <= 120 ? undefined : 'Enter your age in whole years, from 1 to 120.',
      gender: sex ? undefined : 'Choose female or male.',
      bmi: bmiInRange(bmi)
        ? undefined
        : mode === 'bmi'
          ? `Enter a BMI from ${BMI_MIN} to ${BMI_MAX}, or work it out from your height and weight.`
          : `Enter your height and weight. They give a BMI of ${bmi === null ? '—' : fmtNumber(bmi)}; it must be from ${BMI_MIN} to ${BMI_MAX}.`,
    };
    setErrors(next);
    const firstBad = (Object.keys(next) as (keyof Errors)[]).find((k) => next[k]);
    if (firstBad || !type || !sex || !bmiInRange(bmi)) {
      formRef.current?.querySelector<HTMLElement>(`[data-field="${firstBad}"] input`)?.focus();
      return;
    }
    setBusy(true);
    try {
      await onSubmit({ diabetes_type: type, age: ageN, gender: sex, bmi: Math.round(bmi * 10) / 10, unit });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form ref={formRef} className="form profile-form" onSubmit={(e) => void submit(e)} noValidate>
      <div data-field="diabetes_type">
        <Options
          name="diabetes_type"
          legend="Diabetes type"
          hint="The model learned different glucose patterns for each type."
          value={type}
          options={[
            { value: 'T1D', label: 'Type 1' },
            { value: 'T2D', label: 'Type 2' },
          ]}
          onChange={setType}
          error={errors.diabetes_type}
        />
      </div>

      <div data-field="age">
        <Field id={`${id}-age`} label="Age" hint="In years. Glucose responses change with age." error={errors.age}>
          <input
            id={`${id}-age`}
            className="input-short"
            name="age"
            type="number"
            inputMode="numeric"
            min={1}
            max={120}
            step={1}
            value={age}
            onChange={(e) => setAge(e.target.value)}
            aria-invalid={errors.age ? true : undefined}
            aria-describedby={describedBy(`${id}-age`, true, Boolean(errors.age))}
          />
        </Field>
      </div>

      <div data-field="gender">
        <Options
          name="gender"
          legend="Sex"
          hint="The model was trained with sex recorded as female or male only, so those are the two choices."
          value={sex}
          options={[
            { value: 'F', label: 'Female' },
            { value: 'M', label: 'Male' },
          ]}
          onChange={setSex}
          error={errors.gender}
        />
      </div>

      <fieldset className="field bmi-field" data-field="bmi">
        <legend>Body-mass index (BMI)</legend>
        <div className="options">
          <label className="option">
            <input type="radio" name="bmi-mode" checked={mode === 'measure'} onChange={() => setMode('measure')} />
            <span>Work it out from height and weight</span>
          </label>
          <label className="option">
            <input type="radio" name="bmi-mode" checked={mode === 'bmi'} onChange={() => setMode('bmi')} />
            <span>I know my BMI</span>
          </label>
        </div>
        {mode === 'bmi' ? (
          <Field id={`${id}-bmi`} label="BMI" error={null}>
            <input
              id={`${id}-bmi`}
              className="input-short"
              name="bmi"
              type="text"
              inputMode="decimal"
              value={bmiText}
              onChange={(e) => setBmiText(e.target.value)}
              aria-invalid={errors.bmi ? true : undefined}
              aria-describedby={describedBy(`${id}-bmi-group`, true, Boolean(errors.bmi))}
            />
          </Field>
        ) : (
          <div className="measure">
            <div className="field">
              <label htmlFor={`${id}-system`}>Units</label>
              <select id={`${id}-system`} value={system} onChange={(e) => setSystem(e.target.value as System)}>
                <option value="metric">cm and kg</option>
                <option value="imperial">feet, inches and pounds</option>
              </select>
            </div>
            {system === 'metric' ? (
              <div className="measure-inputs">
                <Field id={`${id}-cm`} label="Height, cm">
                  <input id={`${id}-cm`} name="height-cm" className="input-short" type="text" inputMode="decimal" value={cm} onChange={(e) => setCm(e.target.value)} />
                </Field>
                <Field id={`${id}-kg`} label="Weight, kg">
                  <input id={`${id}-kg`} name="weight-kg" className="input-short" type="text" inputMode="decimal" value={kg} onChange={(e) => setKg(e.target.value)} />
                </Field>
              </div>
            ) : (
              <div className="measure-inputs">
                <Field id={`${id}-ft`} label="Height, feet">
                  <input id={`${id}-ft`} name="height-ft" className="input-short" type="text" inputMode="numeric" value={ft} onChange={(e) => setFt(e.target.value)} />
                </Field>
                <Field id={`${id}-in`} label="and inches">
                  <input id={`${id}-in`} name="height-in" className="input-short" type="text" inputMode="decimal" value={inch} onChange={(e) => setInch(e.target.value)} />
                </Field>
                <Field id={`${id}-lb`} label="Weight, pounds">
                  <input id={`${id}-lb`} name="weight-lb" className="input-short" type="text" inputMode="decimal" value={lb} onChange={(e) => setLb(e.target.value)} />
                </Field>
              </div>
            )}
            <p className="bmi-result">
              Your BMI:{' '}
              <output className="num" htmlFor={system === 'metric' ? `${id}-cm ${id}-kg` : `${id}-ft ${id}-in ${id}-lb`} aria-live="polite">
                {computed === null ? '—' : fmtNumber(computed)}
              </output>
            </p>
          </div>
        )}
        <p id={`${id}-bmi-group-hint`} className="field-hint">
          Body size changes how glucose responds to food and insulin. The service accepts {BMI_MIN} to {BMI_MAX}.
        </p>
        {errors.bmi ? <FieldError id={`${id}-bmi-group-error`}>{errors.bmi}</FieldError> : null}
      </fieldset>

      {withUnits ? (
        <Options
          name="unit"
          legend="Glucose units"
          hint="Use the unit your meter or sensor shows. 100 mg/dL is 5.6 mmol/L. You can change it later in Settings."
          value={unit}
          options={UNITS.map((u) => ({ value: u, label: u }))}
          onChange={setUnit}
        />
      ) : null}

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="form-actions">
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? busyLabel : submitLabel}
        </button>
        {footer}
      </div>
    </form>
  );
}
