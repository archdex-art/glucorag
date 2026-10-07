package org.glucorag.app.source

import org.glucorag.shared.CgmReading
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * A made-up but plausible CGM trace, for trying GlucoRAG without a sensor. It repeats every 6 h:
 * steady, a meal rise to about 210 mg/dL, then a slow fall to just under 70 mg/dL (so the forecast
 * and the low alert have something to do) and a recovery. Values are a pure function of time, so
 * the backfill and the live readings join into one smooth line, and a restart continues it.
 */
object SimulatedFeed {
    /** [CgmReading.from] of every simulated reading. */
    const val FROM = "simulated"
    const val STEP_MS = 5 * 60_000L
    const val BACKFILL_MS = 3 * 60 * 60_000L

    private const val MINUTE_MS = 60_000.0
    private const val CYCLE_MS = 6 * 60 * 60_000L
    private const val WIGGLE_MGDL = 3.0
    private const val WIGGLE_PERIOD_MS = 45 * 60_000.0

    /** (minute in the 6-hour cycle, mg/dL); the last point equals the first, so the cycle closes. */
    private val KEYS = listOf(
        0.0 to 118.0,
        20.0 to 122.0,
        80.0 to 212.0,
        120.0 to 195.0,
        240.0 to 92.0,
        295.0 to 63.0,
        320.0 to 66.0,
        360.0 to 118.0,
    )

    /** The simulated glucose at [t] (epoch ms), mg/dL. */
    fun mgdlAt(t: Long): Double {
        val minute = Math.floorMod(t, CYCLE_MS) / MINUTE_MS
        val i = KEYS.indexOfLast { it.first <= minute }.coerceAtMost(KEYS.size - 2)
        val (m0, v0) = KEYS[i]
        val (m1, v1) = KEYS[i + 1]
        // Cosine easing: flat at every key point, so the joins have no corners.
        val f = (1 - cos(PI * (minute - m0) / (m1 - m0))) / 2
        return v0 + (v1 - v0) * f + WIGGLE_MGDL * sin(2 * PI * t / WIGGLE_PERIOD_MS)
    }

    /** The reading for the 5-minute slot at [t]; the rate is the change since the previous slot. */
    fun readingAt(t: Long): CgmReading {
        val mgdl = mgdlAt(t)
        return CgmReading(t, mgdl, (mgdl - mgdlAt(t - STEP_MS)) / (STEP_MS / MINUTE_MS), FROM)
    }

    /** The 5-minute slot [t] falls in (slots start at multiples of 5 min since the epoch). */
    fun slot(t: Long): Long = Math.floorDiv(t, STEP_MS) * STEP_MS

    /** Readings for every slot after [afterT] up to [nowMs], oldest first, never more than the last 3 h. */
    fun readings(afterT: Long?, nowMs: Long): List<CgmReading> {
        val last = slot(nowMs)
        val first = slot(maxOf(afterT ?: Long.MIN_VALUE, nowMs - BACKFILL_MS)) + STEP_MS
        return (first..last step STEP_MS).map(::readingAt)
    }
}
