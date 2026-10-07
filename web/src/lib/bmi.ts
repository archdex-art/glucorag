/** Body-mass index from height and weight, in metric or imperial units. */

/** The range the service accepts (glucorag.api.me.ProfileIn). */
export const BMI_MIN = 10;
export const BMI_MAX = 80;

const CM_PER_INCH = 2.54;
const KG_PER_LB = 0.45359237;

/** kg / m², one decimal; null when either input is missing or not positive. */
export function bmiMetric(heightCm: number, weightKg: number): number | null {
  if (!(heightCm > 0) || !(weightKg > 0) || !Number.isFinite(heightCm) || !Number.isFinite(weightKg)) return null;
  const m = heightCm / 100;
  return Math.round((weightKg / (m * m)) * 10) / 10;
}

/** BMI from feet + inches and pounds (converted exactly to cm and kg). */
export function bmiImperial(feet: number, inches: number, pounds: number): number | null {
  const ft = Number.isFinite(feet) ? feet : 0;
  const inch = Number.isFinite(inches) ? inches : 0;
  if (ft < 0 || inch < 0) return null;
  return bmiMetric((ft * 12 + inch) * CM_PER_INCH, pounds * KG_PER_LB);
}

export function bmiInRange(bmi: number | null): bmi is number {
  return bmi !== null && bmi >= BMI_MIN && bmi <= BMI_MAX;
}

export type MeasureSystem = 'metric' | 'imperial';

/** Regions that measure height and weight in feet/inches and pounds. */
const IMPERIAL_REGION: Record<string, true> = { US: true, LR: true, MM: true };

/**
 * Default height/weight system from a BCP 47 locale's region (`en-US` → imperial,
 * `en-IN` → metric). Glucose units are no guide: mg/dL is standard in many metric countries.
 */
export function defaultMeasureSystem(locale: string | undefined): MeasureSystem {
  if (!locale) return 'metric';
  let region: string | undefined;
  try {
    region = new Intl.Locale(locale).maximize().region;
  } catch {
    region = undefined;
  }
  return region && IMPERIAL_REGION[region.toUpperCase()] ? 'imperial' : 'metric';
}
