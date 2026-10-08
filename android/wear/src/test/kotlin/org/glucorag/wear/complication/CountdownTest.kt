package org.glucorag.wear.complication

import org.glucorag.shared.Forecast
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Risk
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CountdownTest {
    private val now = 1_791_385_800_000L
    private val min = 60_000L

    private fun snapshot(mgdl: Double, risk: Risk?) = Snapshot(
        v = 1, unit = GlucoseUnit.MG_DL, now = Now(now - min, mgdl, -1.0, "juggluco"), recent = emptyList(),
        forecast = Forecast(now - min, listOf(15, 30, 45, 60), listOf(80.0, 70.0, 65.0, 62.0), listOf(75.0, 62.0, 58.0, 55.0), listOf(85.0, 78.0, 72.0, 70.0)),
        risk = risk, server = Server("ok", now), written = now,
    )

    /** A predicted low counts down live on the face, so the minutes never go stale between pushes. */
    @Test
    fun predictedLowCountsDownToTheRiskTime() {
        val at = now + 14 * min
        assertEquals(at, countdownTarget(snapshot(90.0, Risk("hypo", at, "medium")), now))
    }

    @Test
    fun lowAlreadyNowHasNoCountdown() {
        assertNull(countdownTarget(snapshot(65.0, Risk("hypo", now + 14 * min, "medium")), now))
    }

    @Test
    fun riskTimeInThePastHasNoCountdown() {
        assertNull(countdownTarget(snapshot(90.0, Risk("hypo", now - min, "medium")), now))
    }

    @Test
    fun noRiskNoCountdown() {
        assertNull(countdownTarget(snapshot(120.0, null), now))
    }

    /** The countdown names the threshold, not the furthest value: that comes later than the crossing. */
    @Test
    fun longTextCountsDownToCrossingTheThresholdInTheUnit() {
        assertEquals("Below 70 in ^1", countdownTemplate(Risk("hypo", now, "medium", 61.0), GlucoseUnit.MG_DL))
        assertEquals("Above 180 in ^1", countdownTemplate(Risk("hyper", now, "medium", 205.0), GlucoseUnit.MG_DL))
        assertEquals("Below 3.9 in ^1", countdownTemplate(Risk("hypo", now, "medium"), GlucoseUnit.MMOL_L))
        assertEquals("Above 10.0 in ^1", countdownTemplate(Risk("hyper", now, "medium"), GlucoseUnit.MMOL_L))
    }
}
