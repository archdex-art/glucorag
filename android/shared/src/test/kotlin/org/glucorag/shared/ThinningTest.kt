package org.glucorag.shared

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ThinningTest {
    private val t0 = 1_759_738_800_000L

    @Test
    fun firstReadingQueued() {
        assertTrue(Thinner(null).shouldKeep(t0))
    }

    @Test
    fun oneMinuteInputQueuesOneInFive() {
        val thinner = Thinner(null)
        val queued = (0 until 20).map { t0 + it * 60_000L }.filter { thinner.shouldKeep(it) }
        assertEquals(listOf(0, 5, 10, 15).map { t0 + it * 60_000L }, queued)
        assertEquals(t0 + 15 * 60_000L, thinner.lastKeptT)
    }

    @Test
    fun exactly270sQueued() {
        val thinner = Thinner(t0)
        assertFalse(thinner.shouldKeep(t0 + 269_999L))
        assertTrue(thinner.shouldKeep(t0 + 270_000L))
        assertEquals(t0 + 270_000L, thinner.lastKeptT)
    }
}
