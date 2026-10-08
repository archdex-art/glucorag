package org.glucorag.wear.ui

import org.glucorag.shared.FRESH_MS
import org.glucorag.shared.Snapshot
import org.glucorag.shared.formatGlucose
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private const val MINUTE_MS = 60_000L
private val HH_MM: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

/** Local "HH:mm" for an epoch-ms time. */
fun clockTime(t: Long, zone: ZoneId = ZoneId.systemDefault()): String =
    HH_MM.format(Instant.ofEpochMilli(t).atZone(zone))

/** Whole minutes since [t], never negative. */
fun minutesSince(t: Long, nowMs: Long): Long = ((nowMs - t) / MINUTE_MS).coerceAtLeast(0)

/** "4 min ago". */
fun ageText(t: Long, nowMs: Long): String = "${minutesSince(t, nowMs)} min ago"

/** True once the current reading is [FRESH_MS] old (or missing): show it grey with "Old reading". */
fun isOld(s: Snapshot, nowMs: Long): Boolean = s.now?.let { nowMs - it.t >= FRESH_MS } ?: true

/**
 * "In 60 min: 7.8–9.4": the alert band at [horizon] minutes after the forecast time, in the
 * account unit; null without that horizon or once it has passed.
 */
fun bandText(s: Snapshot, horizon: Int, nowMs: Long): String? {
    val f = s.forecast ?: return null
    val i = f.horizons.indexOf(horizon)
    if (i < 0 || i >= f.low.size || i >= f.high.size) return null
    if (nowMs >= f.t0 + horizon * MINUTE_MS) return null
    return "In $horizon min: ${formatGlucose(f.low[i], s.unit)}–${formatGlucose(f.high[i], s.unit)}"
}
