package org.glucorag.app.ui

import org.glucorag.app.data.SyncState
import org.glucorag.app.data.SyncSummary
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.ZoneId

class PhoneTextsTest {
    private val zone = ZoneId.of("Asia/Kolkata")
    /** 2026-10-06T14:05:00+05:30. */
    private val t1405 = 1_759_739_700_000L
    private val min = 60_000L

    @Test
    fun ageReadsJustNowMinutesHours() {
        assertEquals("just now", ageText(t1405, t1405 + 30_000L))
        assertEquals("1 min ago", ageText(t1405, t1405 + min))
        assertEquals("59 min ago", ageText(t1405, t1405 + 59 * min + 59_000L))
        assertEquals("1 h 5 min ago", ageText(t1405, t1405 + 65 * min))
        assertEquals("3 h ago", ageText(t1405, t1405 + 180 * min))
    }

    @Test
    fun syncLineForEachState() {
        val now = t1405 + 2 * min
        assertEquals("Not uploaded yet.", syncLine(null, 0, now, zone))
        assertEquals("Uploaded 2 min ago.", syncLine(SyncSummary(SyncState.SYNCED, t1405, t1405, 0), 0, now, zone))
        assertEquals(
            "Uploaded 2 min ago. 2 readings refused.",
            syncLine(SyncSummary(SyncState.SYNCED, t1405, t1405, 2), 0, now, zone),
        )
        assertEquals(
            "Server unreachable since 14:05. 6 readings waiting.",
            syncLine(SyncSummary(SyncState.UNREACHABLE, now, t1405, 0), 6, now, zone),
        )
        assertEquals(
            "Server unreachable since 14:05. 1 reading waiting.",
            syncLine(SyncSummary(SyncState.UNREACHABLE, now, t1405, 0), 1, now, zone),
        )
        assertEquals("Signed out on the server. Sign in again.", syncLine(SyncSummary(SyncState.SIGNED_OUT, now, now, 0), 3, now, zone))
        assertEquals("Enter your details to start the forecast.", syncLine(SyncSummary(SyncState.NEEDS_SETUP, now, now, 0), 0, now, zone))
    }

    @Test
    fun syncedWithWaitingReadingsSaysSo() {
        assertEquals(
            "Uploaded 2 min ago. 1 reading waiting.",
            syncLine(SyncSummary(SyncState.SYNCED, t1405, t1405, 0), 1, t1405 + 2 * min, zone),
        )
    }

    @Test
    fun sourceNamesForEachSource() {
        assertEquals("Juggluco", sourceName("juggluco"))
        assertEquals("xDrip+", sourceName("xdrip"))
        assertEquals("Simulated", sourceName("simulated"))
        assertEquals("No readings received yet", sourceName(null))
    }
}
