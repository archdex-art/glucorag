package org.glucorag.app.ui

import org.glucorag.shared.GlucoseUnit
import kotlin.math.roundToLong

// Body-mass index and default units, as on the website (`web/src/lib/bmi.ts`).

/** The range the server accepts (glucorag.api.me.ProfileIn). */
const val BMI_MIN = 10.0
const val BMI_MAX = 80.0

const val CM_PER_INCH = 2.54
const val KG_PER_LB = 0.45359237

/** kg / m², one decimal; null when either input is missing, not finite or not positive. */
fun bmiMetric(heightCm: Double?, weightKg: Double?): Double? {
    if (heightCm == null || weightKg == null || !heightCm.isFinite() || !weightKg.isFinite()) return null
    if (heightCm <= 0 || weightKg <= 0) return null
    val m = heightCm / 100
    return round1(weightKg / (m * m))
}

/** BMI from feet + inches and pounds (converted exactly to cm and kg); a missing part counts as 0. */
fun bmiImperial(feet: Double?, inches: Double?, pounds: Double?): Double? {
    val ft = feet?.takeIf { it.isFinite() } ?: 0.0
    val inch = inches?.takeIf { it.isFinite() } ?: 0.0
    if (ft < 0 || inch < 0) return null
    return bmiMetric(feetInchesToCm(ft, inch), pounds?.let(::poundsToKg))
}

fun feetInchesToCm(feet: Double, inches: Double): Double = (feet * 12 + inches) * CM_PER_INCH

fun poundsToKg(pounds: Double): Double = pounds * KG_PER_LB

fun bmiInRange(bmi: Double?): Boolean = bmi != null && bmi >= BMI_MIN && bmi <= BMI_MAX

/** One decimal, half away from zero (like the website's Math.round for positive values). */
fun round1(v: Double): Double = (v * 10).roundToLong() / 10.0

/** "23.4" for 23.4, "23" for 23.0. */
fun bmiText(bmi: Double): String = if (bmi == Math.floor(bmi)) bmi.toLong().toString() else bmi.toString()

/** A number typed in any locale: "23,5" and "23.5" both read 23.5; blank or junk → null. */
fun parseNumber(text: String): Double? = text.trim().replace(',', '.').toDoubleOrNull()?.takeIf { it.isFinite() }

/** Regions that measure height and weight in feet/inches and pounds. */
private val IMPERIAL_REGIONS = setOf("US", "LR", "MM")

/** Whether height and weight default to feet/inches and pounds for an ISO 3166 [region] ("US"). */
fun usesImperial(region: String?): Boolean = region?.uppercase() in IMPERIAL_REGIONS

/**
 * Regions where glucose meters customarily read mg/dL; elsewhere mmol/L is the norm. Only a
 * default for the setup form: the person picks what their meter shows.
 */
private val MG_DL_REGIONS = setOf(
    "US", "IN", "JP", "KR", "TW", "FR", "BE", "LU", "IT", "ES", "PT", "AT", "DE", "PL", "GR",
    "IL", "EG", "LB", "JO", "SY", "TR", "GE", "DZ", "TN", "BD", "NP", "PK", "PH", "ID", "TH",
    "MX", "BR", "AR", "CL", "CO", "PE", "VE", "EC", "UY", "BO", "PY",
)

/** Default glucose unit for an ISO 3166 [region]: mg/dL where it is customary, mmol/L otherwise. */
fun defaultGlucoseUnit(region: String?): GlucoseUnit =
    if (region?.uppercase() in MG_DL_REGIONS) GlucoseUnit.MG_DL else GlucoseUnit.MMOL_L
