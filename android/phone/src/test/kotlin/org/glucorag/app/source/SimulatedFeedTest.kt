package org.glucorag.app.source

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class SimulatedFeedTest {
    private val step = SimulatedFeed.STEP_MS
    private val now = 1_759_739_712_345L // 2026-10-06T08:35:12.345Z, not on a slot

    /** Two full 6-hour cycles, slot by slot. */
    private val days = (0 until 2 * 72).map { SimulatedFeed.readingAt(SimulatedFeed.slot(now) + it * step) }

    @Test
    fun valuesStayPlausible() {
        days.forEach { assertTrue("${it.mgdl}", it.mgdl in 40.0..400.0) }
    }

    @Test
    fun traceIsSmooth() {
        days.zipWithNext().forEach { (a, b) -> assertTrue("step ${b.mgdl - a.mgdl}", abs(b.mgdl - a.mgdl) <= 15.0) }
    }

    @Test
    fun includesAMealRiseAndASlowFallTowardsLow() {
        val values = days.take(72).map { it.mgdl }
        assertTrue("peak ${values.max()}", values.max() >= 200.0)
        assertTrue("trough ${values.min()}", values.min() < 70.0)
        // From the peak it falls for at least 2 hours before reaching the low.
        val cycle = (0 until 72).map { SimulatedFeed.mgdlAt(it * step) }
        val peak = cycle.indexOf(cycle.max())
        val trough = cycle.indexOf(cycle.min())
        assertTrue("fall of ${(trough - peak) * 5} min", (trough - peak) * 5 >= 120)
    }

    @Test
    fun deterministic() {
        assertEquals(SimulatedFeed.readingAt(now), SimulatedFeed.readingAt(now))
        assertEquals(SimulatedFeed.mgdlAt(now), SimulatedFeed.mgdlAt(now + 6 * 3_600_000L), 1e-6)
    }

    @Test
    fun backfillIsTheLastThreeHoursAtFiveMinuteSpacing() {
        val r = SimulatedFeed.readings(null, now)
        assertEquals(36, r.size)
        assertEquals(SimulatedFeed.slot(now), r.last().t)
        assertTrue(r.last().t <= now)
        assertTrue(r.first().t > now - SimulatedFeed.BACKFILL_MS)
        r.zipWithNext().forEach { (a, b) -> assertEquals(step, b.t - a.t) }
        r.forEach {
            assertEquals(0L, it.t % step)
            assertEquals(SimulatedFeed.FROM, it.from)
        }
    }

    @Test
    fun liveReadingsContinueAfterTheNewestOne() {
        val backfill = SimulatedFeed.readings(null, now)
        assertEquals(emptyList<Any>(), SimulatedFeed.readings(backfill.last().t, now + 60_000L))
        val next = SimulatedFeed.readings(backfill.last().t, now + step)
        assertEquals(listOf(backfill.last().t + step), next.map { it.t })
        // Asleep for 40 minutes: the missed readings arrive together.
        assertEquals(8, SimulatedFeed.readings(backfill.last().t, now + 40 * 60_000L).size)
        // A real reading at an odd time: the next simulated one starts at the following slot.
        assertEquals(SimulatedFeed.slot(now) + step, SimulatedFeed.readings(now, now + step).single().t)
    }

    @Test
    fun rateIsTheChangePerMinuteSinceTheLastSlot() {
        val t = SimulatedFeed.slot(now)
        val r = SimulatedFeed.readingAt(t)
        assertEquals((SimulatedFeed.mgdlAt(t) - SimulatedFeed.mgdlAt(t - step)) / 5.0, r.ratePerMin!!, 1e-9)
    }
}
