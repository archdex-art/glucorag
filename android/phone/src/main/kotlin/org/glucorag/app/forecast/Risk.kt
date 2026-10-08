package org.glucorag.app.forecast

import kotlinx.serialization.Serializable
import org.glucorag.shared.HIGH_THRESHOLD_MG_DL
import org.glucorag.shared.LOW_THRESHOLD_MG_DL

/**
 * The server's alert rule (`glucorag/risk/detectors.py`, `glucorag/notify/alerts.py`) on the phone.
 *
 * Status flags ([assess]): hypo when the selected lower quantile is ≤ 70 mg/dL at any horizon,
 * hyper when the selected upper quantile is ≥ 180. Severity: `high` for a level-2 value (≤ 54 or
 * ≥ 250) within 30 min; `medium` for a first crossing within 30 min or a level-2 value later;
 * `low` otherwise.
 *
 * Alerts ([alerting]) are narrower: no low alert while the reading is already ≤ 70, no high alert
 * while it is already ≥ 180, and a high alert also needs the upper quantile to reach 190 at some
 * horizon. [AlertMemory] then raises each condition once on onset, at most once per 30 min.
 */
const val HYPO_LEVEL2_MG_DL = 54.0
const val HYPER_LEVEL2_MG_DL = 250.0
const val URGENT_HORIZON_MIN = 30
const val HYPER_ALERT_MARGIN_MG_DL = 10.0
const val ALERT_COOLDOWN_MS = 30 * 60_000L

/** Alert sensitivity: the forecast quantile each direction reads (`glucorag/api/me.py`). */
enum class Sensitivity(val key: String, val hypoQuantile: Double, val hyperQuantile: Double) {
    STANDARD("standard", 0.25, 0.75),
    CAUTIOUS("cautious", 0.10, 0.90),
    VERY_CAUTIOUS("very_cautious", 0.02, 0.98),
    ;

    companion object {
        fun of(key: String?): Sensitivity = entries.firstOrNull { it.key == key } ?: STANDARD

        /** The named sensitivity for a quantile pair, or null for a custom pair. */
        fun of(hypoQ: Double, hyperQ: Double): Sensitivity? = entries.firstOrNull {
            kotlin.math.abs(it.hypoQuantile - hypoQ) < 1e-9 && kotlin.math.abs(it.hyperQuantile - hyperQ) < 1e-9
        }
    }
}

/**
 * [horizonMin]: the earliest horizon the selected quantile crosses; [valueMgdl] its value there;
 * [extremeMgdl] its most extreme value over all horizons ("could reach").
 */
data class RiskFlag(
    val type: String,
    val horizonMin: Int,
    val quantile: Double,
    val valueMgdl: Double,
    val extremeMgdl: Double,
    val severity: String,
)

private fun severity(firstH: Int, level2Horizons: List<Int>): String = when {
    level2Horizons.any { it <= URGENT_HORIZON_MIN } -> "high"
    firstH <= URGENT_HORIZON_MIN || level2Horizons.isNotEmpty() -> "medium"
    else -> "low"
}

/** Hypo and/or hyper flags for one forecast (both can fire on a wide band), hypo first. */
fun assess(f: QuantileForecast, hypoQ: Double, hyperQ: Double): List<RiskFlag> {
    val flags = mutableListOf<RiskFlag>()
    val lows = f.column(hypoQ)
    val lowCross = f.horizons.indices.filter { lows[it] <= LOW_THRESHOLD_MG_DL }
    if (lowCross.isNotEmpty()) {
        val first = lowCross.first()
        val level2 = f.horizons.indices.filter { lows[it] <= HYPO_LEVEL2_MG_DL }.map { f.horizons[it] }
        flags += RiskFlag("hypo", f.horizons[first], hypoQ, lows[first], lows.min(), severity(f.horizons[first], level2))
    }
    val highs = f.column(hyperQ)
    val highCross = f.horizons.indices.filter { highs[it] >= HIGH_THRESHOLD_MG_DL }
    if (highCross.isNotEmpty()) {
        val first = highCross.first()
        val level2 = f.horizons.indices.filter { highs[it] >= HYPER_LEVEL2_MG_DL }.map { f.horizons[it] }
        flags += RiskFlag("hyper", f.horizons[first], hyperQ, highs[first], highs.max(), severity(f.horizons[first], level2))
    }
    return flags
}

/** The flags that raise an alert given the latest reading [latestMgdl] (see the file comment). */
fun alerting(flags: List<RiskFlag>, latestMgdl: Double): List<RiskFlag> = flags.filter { f ->
    if (f.type == "hypo") {
        latestMgdl > LOW_THRESHOLD_MG_DL
    } else {
        latestMgdl < HIGH_THRESHOLD_MG_DL && f.extremeMgdl >= HIGH_THRESHOLD_MG_DL + HYPER_ALERT_MARGIN_MG_DL
    }
}

/**
 * `AlertDeduplicator` for one alert type: onset raises unless the same type was raised less
 * than [ALERT_COOLDOWN_MS] before (the condition then turns active silently); while active
 * nothing is raised; a cleared condition makes the next onset eligible again. Times are reading
 * times, so a backfill de-duplicates like the live stream.
 */
@Serializable
data class AlertMemory(val active: Boolean = false, val lastRaised: Long? = null) {
    /** The memory after observing the condition [present] at [t], and whether to raise now. */
    fun observe(present: Boolean, t: Long): Pair<AlertMemory, Boolean> {
        if (!present) return copy(active = false) to false
        if (active) return this to false
        if (lastRaised != null && t - lastRaised < ALERT_COOLDOWN_MS) return copy(active = true) to false
        return AlertMemory(active = true, lastRaised = t) to true
    }
}
