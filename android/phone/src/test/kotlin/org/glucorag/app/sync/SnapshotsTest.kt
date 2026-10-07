package org.glucorag.app.sync

import org.glucorag.shared.CgmReading
import org.glucorag.shared.Forecast
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class SnapshotsTest {
    private val base = Snapshot(
        v = 1, unit = GlucoseUnit.MMOL_L, now = Now(1_000L, 140.0, 0.1, "server"),
        recent = listOf(listOf(1_000.0, 140.0)),
        forecast = Forecast(1_000L, listOf(15, 30, 45, 60), listOf(1.0, 2.0, 3.0, 4.0), listOf(1.0, 2.0, 3.0, 4.0), listOf(1.0, 2.0, 3.0, 4.0)),
        risk = null, server = Server("unreachable", 900L), written = 1_001L,
    )

    @Test
    fun newerReadingReplacesNowAndKeepsTheRest() {
        val s = withReading(base, CgmReading(300_000L, 160.0, 1.2, "juggluco"), nowMs = 300_500L)
        assertEquals(Now(300_000L, 160.0, 1.2, "juggluco"), s.now)
        assertEquals(300_500L, s.written)
        assertEquals(base.forecast, s.forecast)
        assertEquals(base.server, s.server)
        assertEquals(listOf(listOf(1_000.0, 140.0), listOf(300_000.0, 160.0)), s.recent)
    }

    @Test
    fun olderReadingLeavesTheSnapshotAlone() {
        assertSame(base, withReading(base, CgmReading(500L, 90.0, null, "xdrip"), nowMs = 2_000L))
    }

    @Test
    fun recentStaysWithin37Points() {
        val full = base.copy(recent = (0 until 37).map { listOf(it * 300_000.0, 100.0) })
        val s = withReading(full, CgmReading(37 * 300_000L, 120.0, null, "xdrip"), nowMs = 37 * 300_000L)
        assertEquals(37, s.recent.size)
        assertEquals(listOf(37 * 300_000.0, 120.0), s.recent.last())
    }
}
