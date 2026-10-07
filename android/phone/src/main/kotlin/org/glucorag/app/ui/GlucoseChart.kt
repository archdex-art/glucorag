package org.glucorag.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import org.glucorag.shared.Snapshot
import org.glucorag.shared.Zone
import kotlin.math.ln

private const val SCALE_MIN = 40.0
private const val SCALE_MAX = 400.0
private const val HOUR_MS = 3_600_000L

/** Fraction up the chart for [mgdl] on the website's 40–400 log scale, clamped. */
private fun yFraction(mgdl: Double): Float =
    ((ln(mgdl.coerceIn(SCALE_MIN, SCALE_MAX)) - ln(SCALE_MIN)) / (ln(SCALE_MAX) - ln(SCALE_MIN))).toFloat()

private val ZONES = listOf(
    Zone.VERY_LOW to (SCALE_MIN to 54.0), Zone.LOW to (54.0 to 70.0), Zone.TARGET to (70.0 to 180.0),
    Zone.HIGH to (180.0 to 250.0), Zone.VERY_HIGH to (250.0 to SCALE_MAX),
)

/**
 * The last 3 h of readings and, when there is a fresh forecast, the next hour's alert band and
 * median: zone tints behind, 70 and 180 rules, readings in ink.
 */
@Composable
fun GlucoseChart(snapshot: Snapshot, nowMs: Long, description: String, modifier: Modifier = Modifier) {
    val c = LocalGr.current
    val forecast = snapshot.forecast?.takeIf { nowMs < it.t0 + HOUR_MS }
    val end = forecast?.let { it.t0 + (it.horizons.lastOrNull() ?: 60) * 60_000L } ?: nowMs
    val start = (forecast?.t0 ?: nowMs) - 3 * HOUR_MS
    Canvas(
        modifier
            .fillMaxWidth()
            .height(200.dp)
            .semantics { contentDescription = description },
    ) {
        fun x(t: Long) = ((t - start).toFloat() / (end - start)) * size.width
        fun y(v: Double) = size.height * (1f - yFraction(v))

        for ((zone, range) in ZONES) {
            val top = y(range.second)
            drawRect(c.zoneTint.getValue(zone), topLeft = Offset(0f, top), size = Size(size.width, y(range.first) - top))
        }
        for (rule in listOf(70.0, 180.0)) {
            drawLine(c.line, Offset(0f, y(rule)), Offset(size.width, y(rule)), strokeWidth = 1.dp.toPx())
        }
        if (forecast != null) {
            val anchor = snapshot.now?.takeIf { it.t <= forecast.t0 }?.mgdl ?: forecast.median.firstOrNull() ?: return@Canvas
            val times = listOf(forecast.t0) + forecast.horizons.map { forecast.t0 + it * 60_000L }
            val highs = listOf(anchor) + forecast.high
            val lows = listOf(anchor) + forecast.low
            val band = Path().apply {
                moveTo(x(times[0]), y(highs[0]))
                for (i in 1 until times.size) lineTo(x(times[i]), y(highs[i]))
                for (i in times.indices.reversed()) lineTo(x(times[i]), y(lows[i]))
                close()
            }
            drawPath(band, c.bandInner.copy(alpha = 0.45f))
            val median = Path().apply {
                moveTo(x(times[0]), y(anchor))
                forecast.median.forEachIndexed { i, v -> lineTo(x(times[i + 1]), y(v)) }
            }
            drawPath(median, c.ink, style = Stroke(1.5.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))))
            drawLine(c.ink2, Offset(x(forecast.t0), 0f), Offset(x(forecast.t0), size.height), strokeWidth = 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 6f)))
        }
        val points = snapshot.recent.filter { it.size == 2 && it[0] >= start }.map { it[0].toLong() to it[1] }
        if (points.size >= 2) {
            val line = Path().apply {
                moveTo(x(points[0].first), y(points[0].second))
                for (p in points.drop(1)) lineTo(x(p.first), y(p.second))
            }
            drawPath(line, c.ink, style = Stroke(2.5.dp.toPx()))
        }
        snapshot.now?.let { drawCircle(c.ink, radius = 4.dp.toPx(), center = Offset(x(it.t), y(it.mgdl))) }
    }
}
