package org.glucorag.shared

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

enum class StatusKind {
    WAITING, OPEN_PHONE, NO_RECENT, COLLECTING, NEEDS_SERVER, NO_FORECAST,
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
private val HH_MM: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

/**
 * What the watch says, following the website's `personStatus.ts`. Rows are checked in order;
 * the first match wins. Times in sentences are local `HH:mm` in [zone].
 */
fun statusOf(s: Snapshot?, nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): StatusLine {
    fun line(kind: StatusKind, sentence: String, text: String = "--", title: String = NEXT_HOUR, urgent: Boolean = false) =
        StatusLine(kind, sentence, text, title, urgent)

    if (s == null) return line(StatusKind.WAITING, "Waiting for your phone")
    val state = s.server.state
    if (state == "signed_out" || state == "needs_setup") {
        return line(StatusKind.OPEN_PHONE, "Open GlucoRAG on your phone", title = "Phone")
    }
    val now = s.now
    if (now == null || nowMs - now.t >= FRESH_MS) return line(StatusKind.NO_RECENT, "No recent reading")
    if (state == "warming_up") return line(StatusKind.COLLECTING, "Collecting readings")
    val forecast = s.forecast
    if (forecast == null || nowMs >= forecast.t0 + FORECAST_LIFETIME_MS) {
        return if (state == "unreachable") {
            line(StatusKind.NEEDS_SERVER, "Forecast needs your GlucoRAG server")
        } else {
            line(StatusKind.NO_FORECAST, "No current forecast")
        }
    }

    val value = now.mgdl
    val risk = s.risk
    if (risk != null) {
        val low = risk.type == "hypo"
        val word = if (low) "Low" else "High"
        val urgent = risk.severity == "high"
        // Inclusive, like the backend alert rule (<= hypo, >= hyper).
        val pastNow = if (low) value <= LOW_THRESHOLD_MG_DL else value >= HIGH_THRESHOLD_MG_DL
        if (pastNow) {
            return line(if (low) StatusKind.LOW_NOW else StatusKind.HIGH_NOW, "$word now", "now", word, urgent)
        }
        val soon = if (low) StatusKind.LOW_SOON else StatusKind.HIGH_SOON
        if (risk.at > nowMs) {
            val minutes = (risk.at - nowMs + MINUTE_MS - 1) / MINUTE_MS
            return line(soon, "$word predicted in $minutes min", "${minutes}m", word, urgent)
        }
        val time = HH_MM.format(Instant.ofEpochMilli(risk.at).atZone(zone))
        return line(soon, "$word predicted for $time", "now", word, urgent)
    }

    // The band stays in range but the reading may not: say both, so the sentence never
    // contradicts the coloured value beside it.
    val back = forecast.horizons.firstOrNull()?.let { "back in range within $it min" } ?: "back in range soon"
    if (value >= HIGH_THRESHOLD_MG_DL) return line(StatusKind.HIGH_NOW, "High now, $back", "now", "High")
    if (value <= LOW_THRESHOLD_MG_DL) return line(StatusKind.LOW_NOW, "Low now, $back", "now", "Low")
    return line(StatusKind.IN_RANGE, "In range for the next hour", "OK")
}
