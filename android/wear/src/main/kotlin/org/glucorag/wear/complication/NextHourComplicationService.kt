package org.glucorag.wear.complication

import android.app.PendingIntent
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.LongTextComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.SuspendingComplicationDataSourceService
import org.glucorag.shared.Snapshot
import org.glucorag.shared.statusOf
import org.glucorag.wear.data.SnapshotStore

/** "Next hour": the status table's SHORT_TEXT (`25m` / `Low`) or the sentence. */
class NextHourComplicationService : SuspendingComplicationDataSourceService() {
    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        nextHourData(request.complicationType, SnapshotStore(this).latest(), System.currentTimeMillis(), openAppIntent(this))

    override fun getPreviewData(type: ComplicationType): ComplicationData? {
        val nowMs = System.currentTimeMillis()
        return nextHourData(type, previewSnapshot(nowMs), nowMs, null)
    }
}

internal fun nextHourData(type: ComplicationType, s: Snapshot?, nowMs: Long, tap: PendingIntent?): ComplicationData? {
    val status = statusOf(s, nowMs)
    val sentence = plain(status.sentence)
    return when (type) {
        ComplicationType.SHORT_TEXT -> ShortTextComplicationData.Builder(plain(status.shortText), sentence)
            .setTitle(plain(status.shortTitle))
            .setTapAction(tap)
            .build()
        ComplicationType.LONG_TEXT -> LongTextComplicationData.Builder(sentence, sentence)
            .setTapAction(tap)
            .build()
        else -> null
    }
}
