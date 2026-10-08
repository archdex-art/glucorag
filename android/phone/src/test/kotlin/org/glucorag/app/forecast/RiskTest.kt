package org.glucorag.app.forecast

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The server's `assess` / `alerting` / `AlertDeduplicator`, case by case. */
class RiskTest {
    private val quantiles = listOf(0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98)
    private val min = 60_000L

    /** Every quantile column = [lows] for q < 0.5, [mids] at 0.5, [highs] above, per horizon. */
    private fun forecast(lows: List<Double>, highs: List<Double>, mids: List<Double> = List(4) { 120.0 }) =
        QuantileForecast(0L, listOf(15, 30, 45, 60), quantiles, (0 until 4).map { h ->
            DoubleArray(7) { q -> if (q < 3) lows[h] else if (q == 3) mids[h] else highs[h] }
        })

    @Test
    fun thresholdsAreInclusiveAndFlagTheEarliestCrossing() {
        val flags = assess(forecast(listOf(90.0, 70.0, 60.0, 65.0), listOf(150.0, 170.0, 180.0, 185.0)), 0.25, 0.75)
        assertEquals(listOf("hypo", "hyper"), flags.map { it.type })
        val (hypo, hyper) = flags
        assertEquals(30, hypo.horizonMin)
        assertEquals(70.0, hypo.valueMgdl, 0.0)
        assertEquals(60.0, hypo.extremeMgdl, 0.0)
        assertEquals("medium", hypo.severity)
        assertEquals(45, hyper.horizonMin)
        assertEquals(185.0, hyper.extremeMgdl, 0.0)
        assertEquals("low", hyper.severity)
        assertTrue(assess(forecast(List(4) { 70.1 }, List(4) { 179.9 }), 0.25, 0.75).isEmpty())
    }

    @Test
    fun severityFromUrgencyAndDepth() {
        fun hypo(vararg lows: Double) = assess(forecast(lows.toList(), List(4) { 150.0 }), 0.25, 0.75).single().severity
        assertEquals("high", hypo(90.0, 54.0, 80.0, 80.0))
        assertEquals("medium", hypo(69.0, 80.0, 80.0, 80.0))
        assertEquals("medium", hypo(90.0, 90.0, 90.0, 50.0))
        assertEquals("low", hypo(90.0, 90.0, 69.0, 60.0))
        val hyper = assess(forecast(List(4) { 100.0 }, listOf(250.0, 200.0, 200.0, 200.0)), 0.25, 0.75).single()
        assertEquals("high", hyper.severity)
    }

    @Test
    fun sensitivitySelectsTheQuantile() {
        val f = QuantileForecast(0L, listOf(15, 30, 45, 60), quantiles, List(4) {
            doubleArrayOf(60.0, 66.0, 75.0, 120.0, 170.0, 185.0, 200.0)
        })
        assertTrue(assess(f, Sensitivity.STANDARD.hypoQuantile, Sensitivity.STANDARD.hyperQuantile).isEmpty())
        assertEquals(listOf("hypo", "hyper"), assess(f, Sensitivity.CAUTIOUS.hypoQuantile, Sensitivity.CAUTIOUS.hyperQuantile).map { it.type })
        assertEquals(Sensitivity.VERY_CAUTIOUS, Sensitivity.of(0.02, 0.98))
        assertEquals(null, Sensitivity.of(0.25, 0.9))
    }

    @Test
    fun noAlertForWhatTheReadingAlreadyShows() {
        val flags = assess(forecast(List(4) { 60.0 }, List(4) { 220.0 }), 0.25, 0.75)
        assertEquals(listOf("hypo", "hyper"), alerting(flags, 120.0).map { it.type })
        assertEquals(listOf("hyper"), alerting(flags, 70.0).map { it.type })
        assertEquals(listOf("hypo"), alerting(flags, 180.0).map { it.type })
        assertEquals(listOf("hypo", "hyper"), alerting(flags, 179.9).map { it.type })
    }

    @Test
    fun highAlertNeedsTenAboveTheThresholdSomewhere() {
        val marginal = assess(forecast(List(4) { 100.0 }, listOf(180.0, 185.0, 189.9, 186.0)), 0.25, 0.75)
        assertEquals(1, marginal.size)
        assertTrue(alerting(marginal, 150.0).isEmpty())
        val clear = assess(forecast(List(4) { 100.0 }, listOf(180.0, 185.0, 190.0, 186.0)), 0.25, 0.75)
        val alert = alerting(clear, 150.0).single()
        // The horizon stays the first crossing of 180.
        assertEquals(15, alert.horizonMin)
        // A low needs no margin.
        assertEquals(1, alerting(assess(forecast(List(4) { 70.0 }, List(4) { 150.0 }), 0.25, 0.75), 150.0).size)
    }

    @Test
    fun memoryRaisesOnOnsetOnceAndHoldsTheCooldown() {
        var m = AlertMemory()
        fun step(present: Boolean, t: Long): Boolean = m.observe(present, t).let { (next, raise) -> m = next; raise }
        assertTrue(step(true, 0))
        assertFalse(step(true, 5 * min))
        assertFalse(step(false, 10 * min))
        // Onset again within 30 min of the last raise: active silently.
        assertFalse(step(true, 29 * min))
        assertFalse(step(false, 31 * min))
        assertTrue(step(true, 35 * min))
        assertFalse(step(false, 40 * min))
        assertFalse(step(true, 64 * min))
        assertFalse(step(false, 65 * min))
        assertTrue(step(true, 65 * min + 30 * min))
    }
}
