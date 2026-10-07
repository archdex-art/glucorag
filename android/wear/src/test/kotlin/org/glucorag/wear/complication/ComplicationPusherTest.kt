package org.glucorag.wear.complication

import org.glucorag.shared.StatusKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ComplicationPusherTest {
    private var clockMs = 0L
    private val clock = { clockMs }

    private fun pusher(lastPush: Long? = 0L, lastKind: StatusKind? = StatusKind.IN_RANGE, lastTile: Long? = 0L) =
        ComplicationPusher(clock, lastPush, lastKind, lastTile)

    @Test
    fun sameKindAt299sDoesNotPush() {
        assertFalse(pusher().shouldPush(StatusKind.IN_RANGE, 299_000L))
    }

    @Test
    fun sameKindAt300sPushes() {
        assertTrue(pusher().shouldPush(StatusKind.IN_RANGE, 300_000L))
    }

    @Test
    fun kindChangeAt10sPushes() {
        assertTrue(pusher().shouldPush(StatusKind.LOW_SOON, 10_000L))
    }

    @Test
    fun firstPushAlwaysPushes() {
        assertTrue(pusher(lastPush = null, lastKind = null).shouldPush(StatusKind.WAITING, 0L))
    }

    @Test
    fun shouldPushDefaultsToTheClock() {
        val p = pusher()
        clockMs = 299_000L
        assertFalse(p.shouldPush(StatusKind.IN_RANGE))
        clockMs = 300_000L
        assertTrue(p.shouldPush(StatusKind.IN_RANGE))
    }

    @Test
    fun markPushedResetsTheWindow() {
        val p = pusher()
        p.markPushed(StatusKind.LOW_SOON, 400_000L)
        assertEquals(400_000L, p.lastPush)
        assertEquals(StatusKind.LOW_SOON, p.lastKind)
        assertFalse(p.shouldPush(StatusKind.LOW_SOON, 699_000L))
        assertTrue(p.shouldPush(StatusKind.LOW_SOON, 700_000L))
    }

    @Test
    fun tileIsLimitedToOncePerMinute() {
        val p = pusher()
        assertFalse(p.shouldRequestTile(59_999L))
        assertTrue(p.shouldRequestTile(60_000L))
        assertTrue(pusher(lastTile = null).shouldRequestTile(0L))
    }

    @Test
    fun decidePushesOnKindChangeAndRecordsIt() {
        val p = pusher()
        val first = p.decide(StatusKind.IN_RANGE, 10_000L)
        assertFalse(first.complications)
        assertFalse(first.tile)

        val changed = p.decide(StatusKind.LOW_SOON, 70_000L)
        assertTrue(changed.complications)
        assertTrue(changed.tile)
        assertEquals(70_000L, p.lastPush)
        assertEquals(70_000L, p.lastTile)
        assertEquals(StatusKind.LOW_SOON, p.lastKind)

        // A second change 20 s later still pushes complications, but the tile waits for the minute.
        val again = p.decide(StatusKind.LOW_NOW, 90_000L)
        assertTrue(again.complications)
        assertFalse(again.tile)
        assertEquals(70_000L, p.lastTile)
    }

    @Test
    fun decideUpdatesTheTileEachMinuteEvenWithoutAComplicationPush() {
        val p = pusher()
        val d = p.decide(StatusKind.IN_RANGE, 120_000L)
        assertFalse(d.complications)
        assertTrue(d.tile)
        assertEquals(0L, p.lastPush)
        assertEquals(120_000L, p.lastTile)
    }

    /** A forecast snapshot seconds after the reading must reach the tile, one window later. */
    @Test
    fun throttledTileIsDeferredToTheEndOfItsWindow() {
        val p = pusher(lastTile = 0L)
        val d = p.decide(StatusKind.IN_RANGE, 10_000L)
        assertFalse(d.tile)
        assertEquals(60_000L, d.retryAt)
    }

    @Test
    fun throttledComplicationIsDeferredToTheEndOfItsWindow() {
        val p = pusher(lastPush = 0L, lastTile = null)
        val d = p.decide(StatusKind.IN_RANGE, 100_000L)
        assertFalse(d.complications)
        assertTrue(d.tile)
        assertEquals(300_000L, d.retryAt)
    }

    @Test
    fun flushPushesOnlyWhatWasHeldBack() {
        val p = pusher(lastPush = 0L, lastTile = null)
        p.decide(StatusKind.IN_RANGE, 100_000L) // tile sent, complications held back
        val early = p.flush(StatusKind.IN_RANGE, 200_000L)
        assertFalse(early.complications)
        assertFalse(early.tile)
        assertEquals(300_000L, early.retryAt)

        val due = p.flush(StatusKind.IN_RANGE, 300_000L)
        assertTrue(due.complications)
        assertFalse(due.tile)
        assertNull(due.retryAt)
        assertNull(p.flush(StatusKind.IN_RANGE, 900_000L).retryAt)
    }

    @Test
    fun nothingHeldBackMeansNoRetry() {
        val d = pusher(lastPush = null, lastKind = null, lastTile = null).decide(StatusKind.WAITING, 0L)
        assertTrue(d.complications)
        assertTrue(d.tile)
        assertNull(d.retryAt)
    }

    @Test
    fun aLaterPushClearsTheHeldBackFlag() {
        val p = pusher(lastPush = 0L, lastTile = 0L)
        p.decide(StatusKind.IN_RANGE, 10_000L) // both held back
        val changed = p.decide(StatusKind.LOW_SOON, 70_000L) // kind change pushes complications; tile window open
        assertTrue(changed.complications)
        assertTrue(changed.tile)
        assertNull(changed.retryAt)
    }
}
