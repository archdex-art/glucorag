package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BroadcastsTest {
    private val nowMs = 1_759_738_800_000L
    private val juggluco = "glucodata.Minute"
    private val xdrip = "com.eveningoutpost.dexdrip.BgEstimate"

    private fun jExtras(mgdl: Any? = 123, time: Any? = nowMs - 30_000L, rate: Any? = 1.5f): Map<String, Any?> =
        mapOf(
            "glucodata.Minute.mgdl" to mgdl,
            "glucodata.Minute.Time" to time,
            "glucodata.Minute.Rate" to rate,
            "glucodata.Minute.glucose" to 6.8f,
            "glucodata.Minute.Alarm" to 0,
            "glucodata.Minute.SerialNumber" to "3MH00XXXX",
        ).filterValues { it != null }

    private fun xExtras(bg: Any? = 140.0, time: Any? = nowMs - 60_000L, slope: Any? = 6.7e-6): Map<String, Any?> =
        mapOf(
            "com.eveningoutpost.dexdrip.Extras.BgEstimate" to bg,
            "com.eveningoutpost.dexdrip.Extras.Time" to time,
            "com.eveningoutpost.dexdrip.Extras.BgSlope" to slope,
        ).filterValues { it != null }

    @Test
    fun jugglucoParsed() {
        val r = parseCgm(juggluco, jExtras(), nowMs)!!
        assertEquals(nowMs - 30_000L, r.t)
        assertEquals(123.0, r.mgdl, 0.0)
        assertEquals(1.5, r.ratePerMin!!, 1e-6)
        assertEquals("juggluco", r.from)
    }

    @Test
    fun jugglucoNanRateIsNull() {
        val r = parseCgm(juggluco, jExtras(rate = Float.NaN), nowMs)!!
        assertNull(r.ratePerMin)
    }

    @Test
    fun jugglucoMissingRateIsNull() {
        val r = parseCgm(juggluco, jExtras(rate = null), nowMs)!!
        assertNull(r.ratePerMin)
    }

    @Test
    fun jugglucoMissingValueOrTimeIsNull() {
        assertNull(parseCgm(juggluco, jExtras(mgdl = null), nowMs))
        assertNull(parseCgm(juggluco, jExtras(time = null), nowMs))
    }

    @Test
    fun xdripParsedWithSlopeConversion() {
        val r = parseCgm(xdrip, xExtras(), nowMs)!!
        assertEquals(nowMs - 60_000L, r.t)
        assertEquals(140.0, r.mgdl, 0.0)
        assertEquals(0.402, r.ratePerMin!!, 1e-9)
        assertEquals("xdrip", r.from)
    }

    @Test
    fun xdripMissingBgEstimateIsNull() {
        assertNull(parseCgm(xdrip, xExtras(bg = null), nowMs))
    }

    @Test
    fun xdripMissingTimeIsNull() {
        assertNull(parseCgm(xdrip, xExtras(time = null), nowMs))
    }

    @Test
    fun xdripMissingSlopeIsNullRate() {
        val r = parseCgm(xdrip, xExtras(slope = null), nowMs)!!
        assertNull(r.ratePerMin)
    }

    @Test
    fun lenientNumericTypes() {
        val r = parseCgm(xdrip, xExtras(bg = 140, time = (nowMs - 60_000L).toDouble(), slope = 6.7e-6f), nowMs)!!
        assertEquals(140.0, r.mgdl, 0.0)
        assertEquals(nowMs - 60_000L, r.t)
        assertEquals(0.402, r.ratePerMin!!, 1e-4)
        val j = parseCgm(juggluco, jExtras(mgdl = 123.0, time = (nowMs - 1).toInt().toLong(), rate = 2), nowMs)!!
        assertEquals(123.0, j.mgdl, 0.0)
        assertEquals(2.0, j.ratePerMin!!, 0.0)
    }

    @Test
    fun nonNumericValueIsNull() {
        assertNull(parseCgm(xdrip, xExtras(bg = "140"), nowMs))
    }

    @Test
    fun futureBeyondTwoMinutesDropped() {
        assertNull(parseCgm(juggluco, jExtras(time = nowMs + 120_001L), nowMs))
        assertEquals(nowMs + 120_000L, parseCgm(juggluco, jExtras(time = nowMs + 120_000L), nowMs)!!.t)
    }

    @Test
    fun outOfRangeDropped() {
        assertNull(parseCgm(xdrip, xExtras(bg = 19.9), nowMs))
        assertNull(parseCgm(xdrip, xExtras(bg = 600.1), nowMs))
        assertEquals(20.0, parseCgm(xdrip, xExtras(bg = 20.0), nowMs)!!.mgdl, 0.0)
        assertEquals(600.0, parseCgm(xdrip, xExtras(bg = 600.0), nowMs)!!.mgdl, 0.0)
    }

    @Test
    fun unknownActionIsNull() {
        assertNull(parseCgm("com.example.Other", jExtras(), nowMs))
        assertNull(parseCgm(null, jExtras(), nowMs))
    }
}
