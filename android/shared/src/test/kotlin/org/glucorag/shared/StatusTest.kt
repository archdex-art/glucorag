package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StatusTest {
    private val min = 60_000L
    private val nowMs = 1_759_738_800_000L // 2025-10-06T08:20:00Z

    private fun forecast(t0: Long = nowMs - 5 * min) = Forecast(
        t0 = t0,
        horizons = listOf(15, 30, 45, 60),
        median = listOf(145.0, 150.0, 154.0, 157.0),
        low = listOf(139.0, 140.0, 140.0, 139.0),
        high = listOf(152.0, 161.0, 170.0, 178.0),
    )

    private fun snap(
        mgdl: Double = 142.0,
        age: Long = 4 * min,
        forecast: Forecast? = forecast(),
        risk: Risk? = null,
        state: String = "ok",
    ) = Snapshot(
        v = 1,
        unit = GlucoseUnit.MG_DL,
        now = Now(t = nowMs - age, mgdl = mgdl, rate = 0.4, from = "juggluco"),
        recent = emptyList(),
        forecast = forecast,
        risk = risk,
        server = Server(state = state, since = nowMs - min),
        written = nowMs - age,
    )

    private fun status(s: Snapshot?) = statusOf(s, nowMs)

    private fun assertLine(line: StatusLine, kind: StatusKind, sentence: String, text: String, title: String) {
        assertEquals(kind, line.kind)
        assertEquals(sentence, line.sentence)
        assertEquals(text, line.shortText)
        assertEquals(title, line.shortTitle)
    }

    @Test
    fun row1WaitingForPhone() {
        assertLine(status(null), StatusKind.WAITING, "Waiting for your phone", "--", "Next 1h")
    }

    @Test
    fun row2OpenPhoneWhenDetailsAreMissing() {
        // Wins even over an old reading.
        assertLine(
            status(snap(state = "needs_setup", age = 60 * min)),
            StatusKind.OPEN_PHONE, "Open GlucoRAG on your phone", "--", "Phone",
        )
    }

    @Test
    fun row3NoRecentReadingAtFifteenMinutes() {
        assertLine(status(snap(age = 15 * min)), StatusKind.NO_RECENT, "No recent reading", "--", "Next 1h")
        assertEquals(StatusKind.IN_RANGE, status(snap(age = 15 * min - 1_000)).kind)
        assertEquals(StatusKind.IN_RANGE, status(snap(age = 14 * min + 59_000)).kind)
        assertLine(status(snap().copy(now = null)), StatusKind.NO_RECENT, "No recent reading", "--", "Next 1h")
    }

    @Test
    fun row4Collecting() {
        assertLine(
            status(snap(state = "warming_up", forecast = null)),
            StatusKind.COLLECTING, "Collecting readings", "--", "Next 1h",
        )
    }

    @Test
    fun row5NoCurrentForecastAndExpiryBoundary() {
        assertLine(status(snap(forecast = null)), StatusKind.NO_FORECAST, "No current forecast", "--", "Next 1h")
        assertEquals(StatusKind.NO_FORECAST, status(snap(forecast = forecast(t0 = nowMs - 60 * min))).kind)
        assertEquals(StatusKind.IN_RANGE, status(snap(forecast = forecast(t0 = nowMs - 60 * min + 1))).kind)
    }

    @Test
    fun row6PastThresholdNowGivesValueTrendAndWhereItIsHeading() {
        val low = Risk(type = "hypo", at = nowMs + 20 * min, severity = "high", mgdl = 62.0)
        val high = Risk(type = "hyper", at = nowMs + 20 * min, severity = "medium", mgdl = 230.0)
        val lowLine = status(snap(mgdl = 70.0, risk = low))
        // Reading 4 min old: the 30-min horizon is 26 min ahead, said as 25.
        assertLine(lowLine, StatusKind.LOW_NOW, "70 mg/dL, steady. Likely about 150 in 25 min.", "now", "Low")
        assertTrue(lowLine.urgent)
        val highLine = status(snap(mgdl = 198.0, risk = high, age = 0, forecast = forecast(t0 = nowMs)))
        assertLine(highLine, StatusKind.HIGH_NOW, "198 mg/dL, steady. Likely about 150 in 30 min.", "now", "High")
        assertFalse(highLine.urgent)
    }

    @Test
    fun row7HeadingPastTheThresholdWithWhenAndApartHowFar() {
        val line = status(snap(mgdl = 71.0, risk = Risk("hypo", nowMs + 24 * min + 1, "medium", 68.4)))
        assertLine(line, StatusKind.LOW_SOON, "Heading below 70 in about 25 min (could reach 68).", "25m", "Low")
        assertFalse(line.urgent)
        val high = snap(mgdl = 179.0, risk = Risk("hyper", nowMs + 15 * min, "high", 205.0))
        assertLine(status(high), StatusKind.HIGH_SOON, "Heading above 180 in about 15 min (could reach 205).", "15m", "High")
        assertTrue(status(high).urgent)
        val mmol = high.copy(unit = GlucoseUnit.MMOL_L)
        assertEquals("Heading above 10.0 in about 15 min (could reach 11.4).", status(mmol).sentence)
        val lowMmol = snap(mgdl = 71.0, risk = Risk("hypo", nowMs + 40 * min, "low", 61.0)).copy(unit = GlucoseUnit.MMOL_L)
        assertEquals("Heading below 3.9 in about 40 min (could reach 3.4).", status(lowMmol).sentence)
        // Without the value (phone app 0.2) the parenthesis is left out.
        assertEquals("Heading above 180 in about 15 min.", status(snap(mgdl = 179.0, risk = Risk("hyper", nowMs + 15 * min, "low"))).sentence)
    }

    @Test
    fun row8HeadingWhenTheCrossingTimeHasPassed() {
        assertLine(
            status(snap(risk = Risk("hypo", nowMs, "low", 66.0))),
            StatusKind.LOW_SOON, "Heading below 70 soon (could reach 66).", "now", "Low",
        )
        assertEquals("Heading above 180 soon.", riskSentence(Risk("hyper", nowMs, "low"), GlucoseUnit.MG_DL, 0))
    }

    @Test
    fun row9HighOrLowNowWithoutRiskStillSaysWhereItIsHeading() {
        assertLine(
            status(snap(mgdl = 180.0).let { it.copy(now = it.now!!.copy(rate = 2.5)) }),
            StatusKind.HIGH_NOW, "180 mg/dL, rising quickly. Likely about 150 in 25 min.", "now", "High",
        )
        assertLine(
            status(snap(mgdl = 70.0).let { it.copy(now = it.now!!.copy(rate = null)) }),
            StatusKind.LOW_NOW, "70 mg/dL. Likely about 150 in 25 min.", "now", "Low",
        )
        // Every horizon has passed: only the reading is described.
        val late = snap(mgdl = 190.0, forecast = forecast(t0 = nowMs - 60 * min + 1).copy(horizons = listOf(15, 30, 45, 59)))
        assertEquals("190 mg/dL, steady.", status(late).sentence)
    }

    @Test
    fun row10InRange() {
        val line = status(snap(mgdl = 70.1))
        assertLine(line, StatusKind.IN_RANGE, "In range for the next hour.", "OK", "Next 1h")
        assertFalse(line.urgent)
        assertEquals(StatusKind.IN_RANGE, status(snap(mgdl = 179.9)).kind)
    }

    @Test
    fun shortTextsFitSevenCharacters() {
        val lines = mutableListOf<StatusLine>()
        lines += status(null)
        for (state in listOf("ok", "needs_setup", "warming_up")) {
            for (age in listOf(min, 20 * min)) {
                for (f in listOf(null, forecast(), forecast(t0 = nowMs - 2 * 60 * min))) {
                    for (mgdl in listOf(40.0, 70.0, 120.0, 180.0, 400.0)) {
                        lines += status(snap(mgdl = mgdl, age = age, forecast = f, state = state))
                        for (n in 1..60L) {
                            for (type in listOf("hypo", "hyper")) {
                                lines += status(snap(mgdl, age, f, Risk(type, nowMs + n * min, "high"), state))
                                lines += status(snap(mgdl, age, f, Risk(type, nowMs - n * min, "low"), state))
                            }
                        }
                    }
                }
            }
        }
        for (line in lines) {
            assertTrue(line.shortText, line.shortText.length <= 7)
            assertTrue(line.shortTitle, line.shortTitle.length <= 7)
        }
    }
}
