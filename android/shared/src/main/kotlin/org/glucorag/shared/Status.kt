package org.glucorag.shared

enum class StatusKind {
    WAITING, OPEN_PHONE, NO_RECENT, COLLECTING, NO_FORECAST,
    LOW_NOW, HIGH_NOW, LOW_SOON, HIGH_SOON, IN_RANGE,
}

/**
 * The status sentence plus the next-hour SHORT_TEXT complication values ([shortText] and
 * [shortTitle], each ≤ 7 characters). [urgent]: the risk flag has severity `high`.
 */
data class StatusLine(
    val kind: StatusKind,
    val sentence: String,
    val shortText: String,
    val shortTitle: String,
    val urgent: Boolean,
)

/** A reading this old or older is no longer fresh. */
const val FRESH_MS = 15 * 60_000L

/** A forecast expires this long after its `t0`. */
const val FORECAST_LIFETIME_MS = 60 * 60_000L

private const val MINUTE_MS = 60_000L
private const val NEXT_HOUR = "Next 1h"

/** "below 70" / "above 180": the threshold the forecast crosses, in [unit] (3.9 / 10.0 mmol/L). */
fun riskCrossing(risk: Risk, unit: GlucoseUnit): String =
    if (risk.type == "hypo") "below ${formatGlucose(LOW_THRESHOLD_MG_DL, unit)}" else "above ${formatGlucose(HIGH_THRESHOLD_MG_DL, unit)}"

/**
 * "Heading below 70 in about 40 min (could reach 61).": when the forecast first crosses the
 * threshold ([minutes]; "soon" when null or ≤ 0) and, apart, the furthest it could go.
 */
fun riskSentence(risk: Risk, unit: GlucoseUnit, minutes: Long?): String {
    val time = if (minutes != null && minutes > 0) "in about $minutes min" else "soon"
    val reach = risk.mgdl?.let { " (could reach ${formatGlucose(it, unit)})" } ?: ""
    return "Heading ${riskCrossing(risk, unit)} $time$reach."
}

/**
 * "198 mg/dL, steady. Likely about 185 in 30 min.": the reading, its trend, and the median
 * forecast about half an hour from now (minutes rounded to 5); the forecast part is left out
 * once no horizon is still ahead.
 */
private fun nowSentence(s: Snapshot, now: Now, forecast: Forecast, nowMs: Long): String {
    val reading = "${formatGlucose(now.mgdl, s.unit)} ${s.unit.label}" + (trendOf(now.rate)?.let { ", ${it.label}" } ?: "")
    val ahead = forecast.horizons.indices
        .map { it to (forecast.t0 + forecast.horizons[it] * MINUTE_MS - nowMs) }
        .filter { it.second > 0 && it.first < forecast.median.size }
        .minByOrNull { kotlin.math.abs(it.second - 30 * MINUTE_MS) }
        ?: return "$reading."
    val minutes = (((ahead.second + 150_000L) / (5 * MINUTE_MS)) * 5).coerceAtLeast(5)
    return "$reading. Likely about ${formatGlucose(forecast.median[ahead.first], s.unit)} in $minutes min."
}

/**
 * What the phone's Today screen and the watch say, in plain words. Rows are checked in order;
 * the first match wins.
 */
fun statusOf(s: Snapshot?, nowMs: Long): StatusLine {
    fun line(kind: StatusKind, sentence: String, text: String = "--", title: String = NEXT_HOUR, urgent: Boolean = false) =
        StatusLine(kind, sentence, text, title, urgent)

    if (s == null) return line(StatusKind.WAITING, "Waiting for your phone")
    val state = s.server.state
    if (state == "needs_setup") return line(StatusKind.OPEN_PHONE, "Open GlucoRAG on your phone", title = "Phone")
    val now = s.now
    if (now == null || nowMs - now.t >= FRESH_MS) return line(StatusKind.NO_RECENT, "No recent reading")
    if (state == "warming_up") return line(StatusKind.COLLECTING, "Collecting readings")
    val forecast = s.forecast
    if (forecast == null || nowMs >= forecast.t0 + FORECAST_LIFETIME_MS) return line(StatusKind.NO_FORECAST, "No current forecast")

    val value = now.mgdl
    // Inclusive, like the alert rule (<= 70, >= 180).
    val lowNow = value <= LOW_THRESHOLD_MG_DL
    val highNow = value >= HIGH_THRESHOLD_MG_DL
    val risk = s.risk
    if (risk != null) {
        val low = risk.type == "hypo"
        val word = if (low) "Low" else "High"
        val urgent = risk.severity == "high"
        if (if (low) lowNow else highNow) {
            return line(if (low) StatusKind.LOW_NOW else StatusKind.HIGH_NOW, nowSentence(s, now, forecast, nowMs), "now", word, urgent)
        }
        val soon = if (low) StatusKind.LOW_SOON else StatusKind.HIGH_SOON
        if (risk.at > nowMs) {
            val minutes = (risk.at - nowMs + MINUTE_MS - 1) / MINUTE_MS
            return line(soon, riskSentence(risk, s.unit, minutes), "${minutes}m", word, urgent)
        }
        return line(soon, riskSentence(risk, s.unit, null), "now", word, urgent)
    }

    // The band stays in range but the reading may not: the sentence gives the value and where
    // it is heading, so it never contradicts the coloured value beside it.
    if (highNow) return line(StatusKind.HIGH_NOW, nowSentence(s, now, forecast, nowMs), "now", "High")
    if (lowNow) return line(StatusKind.LOW_NOW, nowSentence(s, now, forecast, nowMs), "now", "Low")
    return line(StatusKind.IN_RANGE, "In range for the next hour.", "OK")
}
