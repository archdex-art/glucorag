package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZoneOffset

class StatusTest {
    private val min = 60_000L
    private val nowMs = 1_759_738_800_000L // 2025-10-06T08:20:00Z
    private val utc: ZoneId = ZoneOffset.UTC

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

    private fun status(s: Snapshot?) = statusOf(s, nowMs, utc)

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
    fun row2OpenPhoneWhenSignedOutOrNeedsSetup() {
        for (state in listOf("signed_out", "needs_setup")) {
            // Wins even over an old reading.
            assertLine(
                status(snap(state = state, age = 60 * min)),
                StatusKind.OPEN_PHONE, "Open GlucoRAG on your phone", "--", "Phone",
            )
        }
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
    fun row5NeedsServerWhenUnreachableWithoutForecast() {
        assertLine(
            status(snap(state = "unreachable", forecast = null)),
            StatusKind.NEEDS_SERVER, "Forecast needs your GlucoRAG server", "--", "Next 1h",
        )
        assertLine(
            status(snap(state = "unreachable", forecast = forecast(t0 = nowMs - 60 * min))),
            StatusKind.NEEDS_SERVER, "Forecast needs your GlucoRAG server", "--", "Next 1h",
        )
    }

    @Test
    fun row6NoCurrentForecastAndExpiryBoundary() {
        assertLine(status(snap(forecast = null)), StatusKind.NO_FORECAST, "No current forecast", "--", "Next 1h")
        assertEquals(StatusKind.NO_FORECAST, status(snap(forecast = forecast(t0 = nowMs - 60 * min))).kind)
        assertEquals(StatusKind.IN_RANGE, status(snap(forecast = forecast(t0 = nowMs - 60 * min + 1))).kind)
    }

    @Test
    fun row7PastThresholdNow() {
        val low = Risk(type = "hypo", at = nowMs + 20 * min, severity = "high")
        val high = Risk(type = "hyper", at = nowMs + 20 * min, severity = "medium")
        val lowLine = status(snap(mgdl = 70.0, risk = low))
        assertLine(lowLine, StatusKind.LOW_NOW, "Low now", "now", "Low")
        assertTrue(lowLine.urgent)
        val highLine = status(snap(mgdl = 180.0, risk = high))
        assertLine(highLine, StatusKind.HIGH_NOW, "High now", "now", "High")
        assertFalse(highLine.urgent)
    }

    @Test
    fun row8PredictedInMinutes() {
        val line = status(snap(mgdl = 71.0, risk = Risk("hypo", nowMs + 24 * min + 1, "medium")))
        assertLine(line, StatusKind.LOW_SOON, "Low predicted in 25 min", "25m", "Low")
        assertFalse(line.urgent)
        assertLine(
            status(snap(mgdl = 179.0, risk = Risk("hyper", nowMs + 15 * min, "high"))),
            StatusKind.HIGH_SOON, "High predicted in 15 min", "15m", "High",
        )
        assertTrue(status(snap(mgdl = 179.0, risk = Risk("hyper", nowMs + 15 * min, "high"))).urgent)
    }

    @Test
    fun row9PredictedForLocalTime() {
        val at = nowMs // 08:20 UTC
        assertLine(
            status(snap(risk = Risk("hypo", at, "low"))),
            StatusKind.LOW_SOON, "Low predicted for 08:20", "now", "Low",
        )
        val line = statusOf(snap(risk = Risk("hyper", at - 2 * min, "low")), nowMs, ZoneId.of("Europe/Berlin"))
        assertLine(line, StatusKind.HIGH_SOON, "High predicted for 10:18", "now", "High")
    }

    @Test
    fun row10HighNowBackInRange() {
        assertLine(
            status(snap(mgdl = 180.0)),
            StatusKind.HIGH_NOW, "High now, back in range within 15 min", "now", "High",
        )
    }

    @Test
    fun row11LowNowBackInRange() {
        assertLine(
            status(snap(mgdl = 70.0)),
            StatusKind.LOW_NOW, "Low now, back in range within 15 min", "now", "Low",
        )
    }

    @Test
    fun row12InRange() {
        val line = status(snap(mgdl = 70.1))
        assertLine(line, StatusKind.IN_RANGE, "In range for the next hour", "OK", "Next 1h")
        assertFalse(line.urgent)
        assertEquals(StatusKind.IN_RANGE, status(snap(mgdl = 179.9)).kind)
    }

    @Test
    fun shortTextsFitSevenCharacters() {
        val lines = mutableListOf<StatusLine>()
        lines += status(null)
        for (state in listOf("ok", "unreachable", "signed_out", "needs_setup", "warming_up")) {
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
