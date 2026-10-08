package org.glucorag.app.forecast

import kotlinx.serialization.Serializable
import org.glucorag.app.data.LocalProfile
import org.glucorag.shared.CgmReading
import org.glucorag.shared.Forecast
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Risk
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import java.time.ZoneId

/** A low or high alert to notify: likely from [at] (epoch ms), the forecast could reach [couldReachMgdl]. */
data class LocalAlert(val type: String, val severity: String, val at: Long, val couldReachMgdl: Double, val t0: Long)

/** De-duplication state per alert type, persisted between cycles. */
@Serializable
data class AlertMemories(val hypo: AlertMemory = AlertMemory(), val hyper: AlertMemory = AlertMemory())

/** One cycle's snapshot (for Today and the watch), the alerts to notify, and the new memory. */
class CycleResult(val snapshot: Snapshot, val alerts: List<LocalAlert>, val memory: AlertMemories)

/**
 * The server's prediction cycle (`GlucoseService.ingest`) on the phone: warm-up check, forecast,
 * risk flags for the status, gated alerts with de-duplication. Pure, so it runs on the JVM.
 */
class Forecaster(private val engine: ForecastEngine, private val zone: ZoneId) {
    private val meta = engine.meta

    /**
     * [stored]: the readings kept on the phone (≈ one per 5 min), oldest first, covering at least
     * the model's history span and the chart's 3 hours; [firstSeen] the oldest one kept;
     * [latest] the newest reading received (it may be newer than the newest stored one).
     */
    fun cycle(
        stored: List<CgmReading>,
        firstSeen: Long?,
        latest: CgmReading?,
        profile: LocalProfile?,
        unit: GlucoseUnit,
        memory: AlertMemories,
        nowMs: Long,
    ): CycleResult {
        val newest = stored.lastOrNull()
        val nowPoint = listOfNotNull(latest, newest).maxByOrNull { it.t }?.let { Now(it.t, it.mgdl, it.ratePerMin, it.from) }
        fun result(state: String, forecast: Forecast? = null, risk: Risk? = null, alerts: List<LocalAlert> = emptyList(), mem: AlertMemories = memory) =
            CycleResult(
                Snapshot(SnapshotCodec.VERSION, unit, nowPoint, recent(stored), forecast, risk, Server(state, nowMs), nowMs),
                alerts,
                mem,
            )

        if (profile == null) return result(NEEDS_SETUP)
        if (newest == null) return result(OK)
        if (warmingUp(firstSeen, newest.t)) return result(WARMING_UP)
        // The service clips readings to the sensor range when it stores them.
        val (min, max) = meta.sensorRange
        val history = stored.filter { it.t >= newest.t - meta.historySpanMin * MINUTE_MS }
            .map { it.copy(mgdl = it.mgdl.coerceIn(min, max)) }
        val forecast = try {
            engine.predict(profile.features(), history, zone)
        } catch (e: DataGapException) {
            // No forecast and no alert decision: the alert state carries over.
            return result(OK)
        }
        val flags = assess(forecast, profile.hypoQuantile, profile.hyperQuantile)
        val gated = alerting(flags, history.last().mgdl).associateBy { it.type }
        val alerts = mutableListOf<LocalAlert>()
        val t = forecast.t0
        val fresh = nowMs - t <= ALERT_FRESH_MS
        fun observe(type: String, m: AlertMemory): AlertMemory {
            val flag = gated[type]
            val (next, raise) = m.observe(flag != null, t)
            if (raise && flag != null && fresh) {
                alerts += LocalAlert(type, flag.severity, t + flag.horizonMin * MINUTE_MS, flag.extremeMgdl, t)
            }
            return next
        }
        val nextMemory = AlertMemories(observe("hypo", memory.hypo), observe("hyper", memory.hyper))
        val band = Forecast(t, forecast.horizons, forecast.column(0.5), forecast.column(profile.hypoQuantile), forecast.column(profile.hyperQuantile))
        // The website's order: earliest horizon first, hypo before hyper.
        val first = flags.sortedWith(compareBy({ it.horizonMin }, { if (it.type == "hypo") 0 else 1 })).firstOrNull()
        val risk = first?.let { Risk(it.type, t + it.horizonMin * MINUTE_MS, it.severity, it.extremeMgdl) }
        return result(OK, band, risk, alerts, nextMemory)
    }

    /** `is_warming_up` on wall-clock times: the history doesn't reach the first look-back slot yet. */
    private fun warmingUp(firstSeen: Long?, t0: Long): Boolean {
        if (firstSeen == null) return true
        val step = meta.intervalMin * MINUTE_MS
        val windowStart = ForecastEngine.wallMs(t0, zone) - (meta.lookbackSteps - 1) * step
        return ForecastEngine.wallMs(firstSeen, zone) >= windowStart + step / 2
    }

    /** The chart's points: the 3 h before the newest reading, ≥ 4.5 min apart, at most [RECENT_POINTS]. */
    private fun recent(stored: List<CgmReading>): List<List<Double>> {
        val end = stored.lastOrNull()?.t ?: return emptyList()
        val kept = mutableListOf<CgmReading>()
        for (r in stored) {
            if (r.t < end - RECENT_MS) continue
            if (kept.isEmpty() || r.t - kept.last().t >= THIN_MS) kept += r
        }
        return kept.takeLast(RECENT_POINTS).map { listOf(it.t.toDouble(), it.mgdl) }
    }

    companion object {
        const val OK = "ok"
        const val WARMING_UP = "warming_up"
        const val NEEDS_SETUP = "needs_setup"

        /** Only alerts from a reading at most this old buzz (a backfill replays older ones silently). */
        const val ALERT_FRESH_MS = 15 * 60_000L
        const val RECENT_POINTS = 37
        const val RECENT_MS = 3 * 60 * 60_000L
        const val THIN_MS = 270_000L
        private const val MINUTE_MS = 60_000L
    }
}
