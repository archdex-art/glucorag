package org.glucorag.app.forecast

import org.glucorag.app.data.LocalProfile
import org.glucorag.shared.CgmReading
import org.glucorag.shared.GlucoseUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneOffset

/** The prediction cycle around a stand-in network whose quantiles the test sets. */
class ForecasterTest {
    private val min = 60_000L
    private val now = 1_791_385_800_000L // 2026-10-07T15:10:00Z
    private val meta = DeviceMeta(
        version = "test",
        intervalMin = 15,
        lookbackSteps = 8,
        horizonSteps = 4,
        maxGapMin = 60,
        padSlots = 2,
        quantiles = listOf(0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98),
        glucoseNorm = DeviceMeta.Norm(150.0, 50.0),
        sensorRange = listOf(40.0, 400.0),
        staticEncoder = DeviceMeta.StaticEncoder(
            features = listOf("gender", "age", "bmi", "diabetes_type"),
            categorical = mapOf("gender" to mapOf("F" to 0.0, "M" to 1.0), "diabetes_type" to mapOf("T1D" to 0.0, "T2D" to 1.0)),
            continuous = mapOf("age" to DeviceMeta.Norm(50.0, 15.0), "bmi" to DeviceMeta.Norm(24.0, 4.0)),
        ),
        inputs = listOf("static", "x_enc", "x_dec"),
        output = "quantiles",
    )
    private val profile = LocalProfile(40, "F", 22.5, "T1D")

    /** mg/dL per quantile, the same at every horizon; listed high-to-low to show the engine sorts. */
    private var levels = listOf(160.0, 150.0, 140.0, 130.0, 120.0, 110.0, 100.0)
    private var lastXEnc: Array<FloatArray>? = null
    private val model = QuantileModel { _, xEnc, _ ->
        lastXEnc = xEnc
        Array(4) { FloatArray(7) { q -> ((levels[q] - 150.0) / 50.0).toFloat() } }
    }
    private val forecaster = Forecaster(ForecastEngine(meta, model), ZoneOffset.UTC)

    /** Readings every 5 min up to [end] over [hours], at [mgdl]. */
    private fun feed(end: Long = now, hours: Int = 4, mgdl: Double = 120.0) =
        (hours * 12 downTo 0).map { k -> CgmReading(end - k * 5 * min, mgdl, null, "juggluco") }

    private fun cycle(
        stored: List<CgmReading> = feed(),
        memory: AlertMemories = AlertMemories(),
        p: LocalProfile? = profile,
        at: Long = now,
    ) = forecaster.cycle(stored, stored.firstOrNull()?.t, stored.lastOrNull(), p, GlucoseUnit.MG_DL, memory, at)

    @Test
    fun forecastBandIsTheProfilesQuantilesAndSorted() {
        val r = cycle(p = profile.copy(hypoQuantile = 0.10, hyperQuantile = 0.90))
        val f = r.snapshot.forecast!!
        assertEquals(now, f.t0)
        assertEquals(listOf(15, 30, 45, 60), f.horizons)
        // The stand-in network speaks float32: values come back within a few µg/dL.
        f.median.forEach { assertEquals(130.0, it, 1e-3) }
        f.low.forEach { assertEquals(110.0, it, 1e-3) }
        f.high.forEach { assertEquals(150.0, it, 1e-3) }
        assertEquals("ok", r.snapshot.server.state)
        assertNull(r.snapshot.risk)
        assertTrue(r.alerts.isEmpty())
        assertTrue(r.snapshot.recent.size <= 37)
        assertEquals(now - 180 * min, r.snapshot.recent.first()[0].toLong())
    }

    @Test
    fun needsDetailsBeforeAnything() {
        val r = cycle(p = null)
        assertEquals("needs_setup", r.snapshot.server.state)
        assertNull(r.snapshot.forecast)
        assertEquals(120.0, r.snapshot.now!!.mgdl, 0.0)
    }

    @Test
    fun warmingUpUntilTheHistoryReachesTheFirstSlot() {
        // First reading 105 min before: reaches the oldest of the 8 slots.
        assertEquals("ok", cycle(feed(hours = 2).filter { it.t >= now - 105 * min }).snapshot.server.state)
        // 7.5 min short of it (half a step): still warming up.
        val short = feed(hours = 2).filter { it.t >= now - 95 * min }
        assertEquals("warming_up", cycle(short).snapshot.server.state)
    }

    @Test
    fun lowAlertOnceThenCooldownAndOnlyFromAFreshReading() {
        levels = listOf(50.0, 60.0, 66.0, 90.0, 120.0, 130.0, 140.0)
        val first = cycle()
        val alert = first.alerts.single()
        assertEquals("hypo", alert.type)
        assertEquals(now + 15 * min, alert.at)
        // "Could reach": the furthest the selected quantile (q0.25 for standard) goes.
        assertEquals(66.0, alert.couldReachMgdl, 1e-3)
        assertEquals("medium", alert.severity)
        assertEquals("hypo", first.snapshot.risk!!.type)
        assertEquals(66.0, first.snapshot.risk!!.mgdl!!, 1e-3)
        // Still forecast 5 min later: no second alert.
        val again = cycle(feed(now + 5 * min), first.memory, at = now + 5 * min)
        assertTrue(again.alerts.isEmpty())
        // Raised from a 20-min-old reading (a late backfill): remembered, not notified.
        val stale = cycle(memory = AlertMemories(), at = now + 20 * min)
        assertTrue(stale.alerts.isEmpty())
        assertNotNull(stale.memory.hypo.lastRaised)
    }

    @Test
    fun noLowAlertWhileAlreadyLowButTheStatusStillSaysSo() {
        levels = listOf(50.0, 55.0, 60.0, 65.0, 80.0, 90.0, 100.0)
        val r = cycle(feed(mgdl = 68.0))
        assertTrue(r.alerts.isEmpty())
        assertEquals("hypo", r.snapshot.risk!!.type)
        assertEquals(false, r.memory.hypo.active)
    }

    @Test
    fun marginalHighIsAStatusButNotAnAlert() {
        levels = listOf(120.0, 130.0, 140.0, 160.0, 185.0, 189.0, 195.0)
        val standard = cycle()
        assertEquals("hyper", standard.snapshot.risk!!.type)
        assertTrue(standard.alerts.isEmpty())
        val cautious = cycle(p = profile.copy(hypoQuantile = 0.10, hyperQuantile = 0.90))
        assertTrue(cautious.alerts.isEmpty())
        val veryCautious = cycle(p = profile.copy(hypoQuantile = 0.02, hyperQuantile = 0.98))
        assertEquals("hyper", veryCautious.alerts.single().type)
    }

    @Test
    fun dataGapGivesNoForecastAndKeepsTheAlertState() {
        val memory = AlertMemories(hypo = AlertMemory(active = true, lastRaised = now - 10 * min))
        val gappy = feed().filter { it.t < now - 80 * min || it.t == now }
        val r = cycle(gappy, memory)
        assertEquals("ok", r.snapshot.server.state)
        assertNull(r.snapshot.forecast)
        assertEquals(memory, r.memory)
    }

    @Test
    fun readingsAreClippedToTheSensorRangeLikeTheServerStoresThem() {
        cycle(feed(mgdl = 20.0))
        val glucoseZ = lastXEnc!!.map { it[0].toDouble() }
        glucoseZ.forEach { assertEquals((40.0 - 150.0) / 50.0, it, 1e-6) }
    }
}
