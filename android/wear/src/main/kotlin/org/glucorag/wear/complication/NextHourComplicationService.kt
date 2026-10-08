package org.glucorag.wear.complication

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationText
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.CountDownTimeReference
import androidx.wear.watchface.complications.data.LongTextComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.data.TimeDifferenceComplicationText
import androidx.wear.watchface.complications.data.TimeDifferenceStyle
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.SuspendingComplicationDataSourceService
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Risk
import org.glucorag.shared.Snapshot
import org.glucorag.shared.StatusKind
import org.glucorag.shared.riskCrossing
import org.glucorag.shared.statusOf
import org.glucorag.wear.data.SnapshotStore
import java.time.Instant
import java.util.concurrent.TimeUnit

/** "Next hour": the status table's SHORT_TEXT (`25m` / `Low`) or the sentence. */
class NextHourComplicationService : SuspendingComplicationDataSourceService() {
    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        nextHourData(request.complicationType, SnapshotStore(this).latest(), System.currentTimeMillis(), openAppIntent(this))

    override fun getPreviewData(type: ComplicationType): ComplicationData? {
        val nowMs = System.currentTimeMillis()
        return nextHourData(type, previewSnapshot(nowMs), nowMs, null)
    }
}

/**
 * When the forecast heads low or high, the time it first crosses 70 / 180: the face then counts the
 * minutes down itself, so they stay right between pushes (at most one per 5 min). Null otherwise.
 */
internal fun countdownTarget(s: Snapshot?, nowMs: Long): Long? {
    val kind = statusOf(s, nowMs).kind
    val at = s?.risk?.at ?: return null
    return at.takeIf { (kind == StatusKind.LOW_SOON || kind == StatusKind.HIGH_SOON) && it > nowMs }
}

private fun countdown(at: Long, template: String? = null): ComplicationText =
    TimeDifferenceComplicationText.Builder(TimeDifferenceStyle.SHORT_SINGLE_UNIT, CountDownTimeReference(Instant.ofEpochMilli(at)))
        .setMinimumTimeUnit(TimeUnit.MINUTES)
        .apply { template?.let { setText(it) } }
        .build()

/** The long text's live countdown: "Below 70 in ^1" / "Above 180 in ^1" ("^1" becomes "14m"). */
internal fun countdownTemplate(risk: Risk, unit: GlucoseUnit): String =
    "${riskCrossing(risk, unit).replaceFirstChar(Char::uppercase)} in ^1"

internal fun nextHourData(type: ComplicationType, s: Snapshot?, nowMs: Long, tap: PendingIntent?): ComplicationData? {
    val status = statusOf(s, nowMs)
    val sentence = plain(status.sentence)
    val at = countdownTarget(s, nowMs)
    return when (type) {
        ComplicationType.SHORT_TEXT -> ShortTextComplicationData.Builder(at?.let { countdown(it) } ?: plain(status.shortText), sentence)
            .setTitle(plain(status.shortTitle))
            .setTapAction(tap)
            .build()
        ComplicationType.LONG_TEXT -> LongTextComplicationData.Builder(
            at?.let { t -> s?.risk?.let { countdown(t, countdownTemplate(it, s.unit)) } } ?: sentence,
            sentence,
        )
            .setTapAction(tap)
            .build()
        else -> null
    }
}
