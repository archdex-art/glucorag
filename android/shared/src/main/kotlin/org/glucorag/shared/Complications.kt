package org.glucorag.shared

import kotlin.math.ln

private const val SCALE_MIN_MG_DL = 40.0
private const val SCALE_MAX_MG_DL = 400.0
private val LN_MIN = ln(SCALE_MIN_MG_DL)
private val LN_SPAN = ln(SCALE_MAX_MG_DL) - LN_MIN

/**
 * RANGED_VALUE position in [0, 1]: `(ln v − ln 40) / (ln 400 − ln 40)`, clamped (out-of-range
 * values throw on API 33+). Non-positive and NaN values map to 0.
 */
fun rangedFraction(mgdl: Double): Float {
    if (!(mgdl > 0)) return 0f
    return ((ln(mgdl) - LN_MIN) / LN_SPAN).coerceIn(0.0, 1.0).toFloat()
}

/** Glucose-now SHORT_TEXT: value plus trend arrow, e.g. "142↗" or "7.9↗" (≤ 7 characters); "--" without a reading. */
fun nowShortText(s: Snapshot): String {
    val now = s.now ?: return "--"
    return formatGlucose(now.mgdl, s.unit) + (trendOf(now.rate)?.arrow ?: "")
}

/** Glucose-now LONG_TEXT, e.g. "142 mg/dL, rising, 4 min ago"; "No reading" without one. */
fun nowLongText(s: Snapshot, nowMs: Long): String {
    val now = s.now ?: return "No reading"
    val minutes = ((nowMs - now.t) / 60_000L).coerceAtLeast(0)
    val trend = trendOf(now.rate)?.let { "${it.label}, " } ?: ""
    return "${formatGlucose(now.mgdl, s.unit)} ${s.unit.label}, $trend$minutes min ago"
}
