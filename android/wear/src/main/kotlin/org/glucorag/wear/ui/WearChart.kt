package org.glucorag.wear.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import org.glucorag.shared.FORECAST_LIFETIME_MS
import org.glucorag.shared.HIGH_THRESHOLD_MG_DL
import org.glucorag.shared.LOW_THRESHOLD_MG_DL
import org.glucorag.shared.Snapshot
import org.glucorag.shared.zoneOf

private const val MINUTE_MS = 60_000L
private const val PAST_MS = 3 * 60 * MINUTE_MS
private const val FUTURE_MS = 60 * MINUTE_MS
private const val Y_MIN = 40.0
private const val Y_MAX_DEFAULT = 300.0

/**
 * The last 3 h of readings plus the next hour's band (forecast low/high at `t0 + horizon`),
 * over the 70–180 target range. Not drawn in ambient.
 */
@Composable
fun WearChart(snapshot: Snapshot, nowMs: Long, modifier: Modifier = Modifier) {
    val start = nowMs - PAST_MS
    val end = nowMs + FUTURE_MS
    val points = snapshot.recent.filter { it.size >= 2 && it[0] >= start && it[0] <= nowMs }
    val forecast = snapshot.forecast?.takeIf { nowMs < it.t0 + FORECAST_LIFETIME_MS }
    val band = forecast?.let { f ->
        f.horizons.indices
            .filter { it < f.low.size && it < f.high.size }
            .map { i -> Triple(f.t0 + f.horizons[i] * MINUTE_MS, f.low[i], f.high[i]) }
    }.orEmpty()
    val yMax = (points.map { it[1] } + band.map { it.third })
        .fold(Y_MAX_DEFAULT) { acc, v -> maxOf(acc, v) }

    Canvas(modifier.semantics { contentDescription = "Glucose, last 3 hours and next hour forecast" }) {
        fun x(t: Double) = ((t - start) / (end - start)).toFloat() * size.width
        fun y(v: Double) = (1 - ((v.coerceIn(Y_MIN, yMax) - Y_MIN) / (yMax - Y_MIN))).toFloat() * size.height

        // Target range.
        val top = y(HIGH_THRESHOLD_MG_DL)
        drawRect(Colors.TargetTint, topLeft = Offset(0f, top), size = Size(size.width, y(LOW_THRESHOLD_MG_DL) - top))

        // "Now" divider.
        drawLine(Colors.Ink2, Offset(x(nowMs.toDouble()), 0f), Offset(x(nowMs.toDouble()), size.height), strokeWidth = 1f)

        // Forecast band polygon, anchored at the latest reading when there is one.
        if (forecast != null && band.isNotEmpty()) {
            val anchor = snapshot.now?.let { Pair(it.t.toDouble(), it.mgdl) }
            val path = Path()
            val upper = listOfNotNull(anchor) + band.map { Pair(it.first.toDouble(), it.third) }
            val lower = band.map { Pair(it.first.toDouble(), it.second) }.reversed() + listOfNotNull(anchor)
            (upper + lower).forEachIndexed { i, (t, v) ->
                if (i == 0) path.moveTo(x(t), y(v)) else path.lineTo(x(t), y(v))
            }
            path.close()
            drawPath(path, Colors.BandFill)

            val median = Path()
            val medianPoints = listOfNotNull(anchor) + forecast.horizons.indices
                .filter { it < forecast.median.size }
                .map { Pair((forecast.t0 + forecast.horizons[it] * MINUTE_MS).toDouble(), forecast.median[it]) }
            medianPoints.forEachIndexed { i, (t, v) ->
                if (i == 0) median.moveTo(x(t), y(v)) else median.lineTo(x(t), y(v))
            }
            drawPath(median, Colors.BandMedian, style = Stroke(width = 2f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f))))
        }

        // Readings: a line plus zone-coloured dots.
        if (points.size > 1) {
            val line = Path()
            points.forEachIndexed { i, p -> if (i == 0) line.moveTo(x(p[0]), y(p[1])) else line.lineTo(x(p[0]), y(p[1])) }
            drawPath(line, Colors.Ink2, style = Stroke(width = 2f))
        }
        for (p in points) drawCircle(Colors.zoneFill(zoneOf(p[1])), radius = 3f, center = Offset(x(p[0]), y(p[1])))
    }
}
