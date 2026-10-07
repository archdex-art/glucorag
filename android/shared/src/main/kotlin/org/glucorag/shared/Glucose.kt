package org.glucorag.shared

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Glucose units, as on the website (`web/src/lib/units.ts`). Values travel in mg/dL; mmol/L is a
 * display unit. mg/dL shows as a whole number, mmol/L with one decimal.
 */
@Serializable
enum class GlucoseUnit(val label: String) {
    @SerialName("mg/dL") MG_DL("mg/dL"),
    @SerialName("mmol/L") MMOL_L("mmol/L");

    companion object {
        /** "mg/dL" or "mmol/L"; anything else throws [IllegalArgumentException]. */
        fun parse(s: String): GlucoseUnit =
            entries.firstOrNull { it.label == s } ?: throw IllegalArgumentException("Unknown glucose unit: $s")
    }
}

const val MG_DL_PER_MMOL_L = 18.0182

/** Alert thresholds, mg/dL: a value at or past them counts as low / high now. */
const val LOW_THRESHOLD_MG_DL = 70.0
const val HIGH_THRESHOLD_MG_DL = 180.0

/** A mg/dL value as display text in [unit] ("112" or "6.2"), never "-0"; "—" when not finite. */
fun formatGlucose(mgdl: Double, unit: GlucoseUnit): String {
    if (!mgdl.isFinite()) return "—"
    val v = if (unit == GlucoseUnit.MMOL_L) mgdl / MG_DL_PER_MMOL_L else mgdl
    val digits = if (unit == GlucoseUnit.MMOL_L) 1 else 0
    // Exact binary value rounded half away from zero, like JavaScript's toFixed; BigDecimal has no -0.
    return BigDecimal(v).setScale(digits, RoundingMode.HALF_UP).toPlainString()
}

/** Consensus zones (website `zones.ts`): < 54, < 70, ≤ 180, ≤ 250, above. */
enum class Zone { VERY_LOW, LOW, TARGET, HIGH, VERY_HIGH }

fun zoneOf(mgdl: Double): Zone = when {
    mgdl < 54.0 -> Zone.VERY_LOW
    mgdl < 70.0 -> Zone.LOW
    mgdl <= 180.0 -> Zone.TARGET
    mgdl <= 250.0 -> Zone.HIGH
    else -> Zone.VERY_HIGH
}

/** CGM trend from the rate of change (website `trend.ts`). */
enum class Trend(val arrow: String, val label: String) {
    RISING_QUICKLY("↑", "rising quickly"),
    RISING("↗", "rising"),
    STEADY("→", "steady"),
    FALLING("↘", "falling"),
    FALLING_QUICKLY("↓", "falling quickly"),
}

/** Trend for a rate in mg/dL per minute; null when the rate is missing or NaN. */
fun trendOf(ratePerMin: Double?): Trend? = when {
    ratePerMin == null || ratePerMin.isNaN() -> null
    ratePerMin > 2 -> Trend.RISING_QUICKLY
    ratePerMin > 1 -> Trend.RISING
    ratePerMin >= -1 -> Trend.STEADY
    ratePerMin >= -2 -> Trend.FALLING
    else -> Trend.FALLING_QUICKLY
}
