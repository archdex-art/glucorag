package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ComplicationsTest {
    private val nowMs = 1_759_738_800_000L

    private fun snap(mgdl: Double, rate: Double?, unit: GlucoseUnit, age: Long = 4 * 60_000L) = Snapshot(
        v = 1,
        unit = unit,
        now = Now(t = nowMs - age, mgdl = mgdl, rate = rate, from = "juggluco"),
        recent = emptyList(),
        forecast = null,
        risk = null,
        server = Server(state = "ok", since = nowMs),
        written = nowMs,
    )

    @Test
    fun rangedFractionIsClampedLogPosition() {
        assertEquals(0f, rangedFraction(20.0))
        assertEquals(1f, rangedFraction(600.0))
        assertEquals(0f, rangedFraction(40.0))
        assertEquals(1f, rangedFraction(400.0))
        assertEquals(0.5f, rangedFraction(126.49), 0.001f)
        assertEquals(0f, rangedFraction(0.0))
        assertEquals(0f, rangedFraction(Double.NaN))
    }

    @Test
    fun shortTextExamples() {
        assertEquals("142↗", nowShortText(snap(142.0, 1.5, GlucoseUnit.MG_DL)))
        assertEquals("7.9↗", nowShortText(snap(142.0, 1.5, GlucoseUnit.MMOL_L)))
        assertEquals("142", nowShortText(snap(142.0, null, GlucoseUnit.MG_DL)))
        assertEquals("--", nowShortText(snap(142.0, null, GlucoseUnit.MG_DL).copy(now = null)))
    }

    @Test
    fun shortTextFitsSevenCharacters() {
        val rates = listOf(null, 3.0, 1.5, 0.0, -1.5, -3.0)
        for (unit in GlucoseUnit.entries) {
            for (rate in rates) {
                var mgdl = 39.0
                while (mgdl <= 401.0) {
                    val text = nowShortText(snap(mgdl, rate, unit))
                    assertTrue(text, text.length <= 7)
                    mgdl += 0.25
                }
            }
        }
    }

    @Test
    fun longTextExamples() {
        assertEquals(
            "142 mg/dL, rising, 4 min ago",
            nowLongText(snap(142.0, 1.5, GlucoseUnit.MG_DL, age = 4 * 60_000L + 59_000), nowMs),
        )
        assertEquals(
            "7.9 mmol/L, steady, 0 min ago",
            nowLongText(snap(142.0, 0.4, GlucoseUnit.MMOL_L, age = 0), nowMs),
        )
        assertEquals(
            "142 mg/dL, 4 min ago",
            nowLongText(snap(142.0, null, GlucoseUnit.MG_DL), nowMs),
        )
        assertEquals("No reading", nowLongText(snap(142.0, null, GlucoseUnit.MG_DL).copy(now = null), nowMs))
    }
}
