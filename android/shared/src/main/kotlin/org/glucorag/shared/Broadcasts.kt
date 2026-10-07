package org.glucorag.shared

/** One CGM reading received from a local broadcast. `ratePerMin` is mg/dL per minute. */
data class CgmReading(val t: Long, val mgdl: Double, val ratePerMin: Double?, val from: String)

const val JUGGLUCO_ACTION = "glucodata.Minute"
const val XDRIP_ACTION = "com.eveningoutpost.dexdrip.BgEstimate"

private const val J_MGDL = "glucodata.Minute.mgdl"
private const val J_TIME = "glucodata.Minute.Time"
private const val J_RATE = "glucodata.Minute.Rate"
private const val X_BG = "com.eveningoutpost.dexdrip.Extras.BgEstimate"
private const val X_TIME = "com.eveningoutpost.dexdrip.Extras.Time"
private const val X_SLOPE = "com.eveningoutpost.dexdrip.Extras.BgSlope"

private const val MIN_MGDL = 20.0
private const val MAX_MGDL = 600.0
private const val MAX_FUTURE_MS = 120_000L
private const val MS_PER_MIN = 60_000.0

/**
 * Parses a Juggluco or xDrip+ broadcast (extras already converted from the Bundle).
 * Numeric extras are accepted as any [Number]. Returns null for unknown actions, a missing
 * value or time, values outside 20–600 mg/dL, and times more than 2 minutes after [nowMs].
 */
fun parseCgm(action: String?, extras: Map<String, Any?>, nowMs: Long): CgmReading? {
    val reading = when (action) {
        JUGGLUCO_ACTION -> {
            val mgdl = extras.double(J_MGDL) ?: return null
            val t = extras.long(J_TIME) ?: return null
            CgmReading(t, mgdl, extras.double(J_RATE), "juggluco")
        }
        XDRIP_ACTION -> {
            // xDrip+ omits BgEstimate when it noise-blocks a reading.
            val mgdl = extras.double(X_BG) ?: return null
            val t = extras.long(X_TIME) ?: return null
            // BgSlope is mg/dL per millisecond.
            CgmReading(t, mgdl, extras.double(X_SLOPE)?.times(MS_PER_MIN), "xdrip")
        }
        else -> return null
    }
    if (reading.mgdl !in MIN_MGDL..MAX_MGDL) return null
    if (reading.t - nowMs > MAX_FUTURE_MS) return null
    return reading
}

private fun Map<String, Any?>.double(key: String): Double? =
    (this[key] as? Number)?.toDouble()?.takeIf { it.isFinite() }

private fun Map<String, Any?>.long(key: String): Long? {
    val n = this[key] as? Number ?: return null
    return when (n) {
        is Double, is Float -> n.toDouble().takeIf { it.isFinite() }?.toLong()
        else -> n.toLong()
    }
}
