package org.glucorag.app.ui

import org.glucorag.app.data.SyncState
import org.glucorag.app.data.SyncSummary
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private const val MINUTE_MS = 60_000L
private val HH_MM: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

/** Local "14:05" for [t] (epoch ms). */
fun clockText(t: Long, zone: ZoneId = ZoneId.systemDefault()): String = HH_MM.format(Instant.ofEpochMilli(t).atZone(zone))

/** "just now", "4 min ago", "1 h 5 min ago", "3 h ago". */
fun ageText(t: Long, nowMs: Long): String {
    val minutes = (nowMs - t).coerceAtLeast(0L) / MINUTE_MS
    return when {
        minutes < 1 -> "just now"
        minutes < 60 -> "$minutes min ago"
        minutes % 60 == 0L -> "${minutes / 60} h ago"
        else -> "${minutes / 60} h ${minutes % 60} min ago"
    }
}

private fun readings(n: Int) = if (n == 1) "1 reading" else "$n readings"

/** The Today screen's upload status line. [waiting] readings are still queued. */
fun syncLine(sync: SyncSummary?, waiting: Int, nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): String {
    val waitingText = if (waiting > 0) " ${readings(waiting)} waiting." else ""
    return when (sync?.state) {
        null -> "Not uploaded yet.$waitingText"
        SyncState.SYNCED -> {
            val refused = if (sync.refused > 0) " ${readings(sync.refused)} refused." else ""
            val ago = ageText(sync.at, nowMs).replaceFirstChar { it.lowercase() }
            "Uploaded $ago.$refused$waitingText"
        }
        SyncState.UNREACHABLE -> "Server unreachable since ${clockText(sync.since, zone)}.$waitingText"
        SyncState.SIGNED_OUT -> "Signed out on the server. Sign in again."
        SyncState.NEEDS_SETUP -> "Finish setup on the website."
    }
}
