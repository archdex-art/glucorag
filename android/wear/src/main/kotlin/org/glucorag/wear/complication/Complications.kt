package org.glucorag.wear.complication

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.wear.watchface.complications.data.PlainComplicationText
import org.glucorag.shared.Forecast
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Risk
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import org.glucorag.wear.ui.MainActivity

internal fun plain(text: String) = PlainComplicationText.Builder(text).build()

/** Tap action for every complication: open the app. */
internal fun openAppIntent(context: Context): PendingIntent = PendingIntent.getActivity(
    context,
    0,
    Intent(context, MainActivity::class.java),
    PendingIntent.FLAG_IMMUTABLE,
)

/** Editor preview: 142 mg/dL rising, read 4 min ago, heading below 70 in 25 min (could reach 66). */
internal fun previewSnapshot(nowMs: Long): Snapshot {
    val t = nowMs - 4 * 60_000L
    return Snapshot(
        v = SnapshotCodec.VERSION,
        unit = GlucoseUnit.MG_DL,
        now = Now(t = t, mgdl = 142.0, rate = 1.5, from = "preview"),
        recent = emptyList(),
        forecast = Forecast(t0 = t, horizons = listOf(30, 60), median = listOf(100.0, 75.0), low = listOf(85.0, 60.0), high = listOf(120.0, 95.0)),
        risk = Risk(type = "hypo", at = nowMs + 25 * 60_000L, severity = "medium", mgdl = 66.0),
        server = Server(state = "ok", since = t),
        written = t,
    )
}
