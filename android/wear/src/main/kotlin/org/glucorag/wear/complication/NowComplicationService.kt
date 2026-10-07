package org.glucorag.wear.complication

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.CountUpTimeReference
import androidx.wear.watchface.complications.data.LongTextComplicationData
import androidx.wear.watchface.complications.data.NoDataComplicationData
import androidx.wear.watchface.complications.data.RangedValueComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.data.TimeDifferenceComplicationText
import androidx.wear.watchface.complications.data.TimeDifferenceStyle
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.SuspendingComplicationDataSourceService
import org.glucorag.shared.Snapshot
import org.glucorag.shared.formatGlucose
import org.glucorag.shared.nowLongText
import org.glucorag.shared.nowShortText
import org.glucorag.shared.rangedFraction
import org.glucorag.wear.data.SnapshotStore
import java.time.Instant
import java.util.concurrent.TimeUnit

/** "Glucose now": value + arrow with its age, the long sentence, or the value on a log scale. */
class NowComplicationService : SuspendingComplicationDataSourceService() {
    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        nowData(request.complicationType, SnapshotStore(this).latest(), System.currentTimeMillis(), openAppIntent(this))

    override fun getPreviewData(type: ComplicationType): ComplicationData? {
        val nowMs = System.currentTimeMillis()
        return nowData(type, previewSnapshot(nowMs), nowMs, null)
    }
}

internal fun nowData(type: ComplicationType, s: Snapshot?, nowMs: Long, tap: PendingIntent?): ComplicationData? {
    val now = s?.now
    if (s == null || now == null) {
        return when (type) {
            ComplicationType.SHORT_TEXT -> ShortTextComplicationData.Builder(plain("--"), plain("No glucose reading"))
                .setTapAction(tap).build()
            ComplicationType.LONG_TEXT -> LongTextComplicationData.Builder(plain("No reading"), plain("No glucose reading"))
                .setTapAction(tap).build()
            ComplicationType.RANGED_VALUE -> NoDataComplicationData()
            else -> null
        }
    }
    val description = plain(nowLongText(s, nowMs))
    return when (type) {
        ComplicationType.SHORT_TEXT -> {
            val age = TimeDifferenceComplicationText.Builder(
                TimeDifferenceStyle.SHORT_SINGLE_UNIT,
                CountUpTimeReference(Instant.ofEpochMilli(now.t)),
            ).setMinimumTimeUnit(TimeUnit.MINUTES).build()
            ShortTextComplicationData.Builder(plain(nowShortText(s)), description)
                .setTitle(age)
                .setTapAction(tap)
                .build()
        }
        ComplicationType.LONG_TEXT -> LongTextComplicationData.Builder(description, description)
            .setTapAction(tap)
            .build()
        ComplicationType.RANGED_VALUE -> RangedValueComplicationData.Builder(rangedFraction(now.mgdl), 0f, 1f, description)
            .setText(plain(formatGlucose(now.mgdl, s.unit)))
            .setTapAction(tap)
            .build()
        else -> null
    }
}
