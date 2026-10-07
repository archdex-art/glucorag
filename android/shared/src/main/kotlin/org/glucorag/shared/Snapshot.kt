package org.glucorag.shared

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * What the phone sends the watch (`v: 1`, < 2 KB). All times are epoch ms; glucose is mg/dL.
 * [forecast] and [risk] are null without a fresh forecast.
 */
@Serializable
data class Snapshot(
    val v: Int,
    val unit: GlucoseUnit,
    val now: Now?,
    /** Last 3 h at 5-min resolution (≤ 37 points), each `[t, mgdl]`. */
    val recent: List<List<Double>>,
    val forecast: Forecast?,
    val risk: Risk?,
    val server: Server,
    val written: Long,
)

/** The latest reading; [rate] in mg/dL per minute, [from] the source app. */
@Serializable
data class Now(val t: Long, val mgdl: Double, val rate: Double?, val from: String)

/** Forecast made at [t0]; [low]/[high] are the user's alert band, per horizon in minutes. */
@Serializable
data class Forecast(
    val t0: Long,
    val horizons: List<Int>,
    val median: List<Double>,
    val low: List<Double>,
    val high: List<Double>,
)

/** The earliest risk flag: [type] `hypo` | `hyper`, [severity] `high` | `medium` | `low`. */
@Serializable
data class Risk(val type: String, val at: Long, val severity: String)

/** [state] is one of `ok | unreachable | signed_out | needs_setup | warming_up`. */
@Serializable
data class Server(val state: String, val since: Long)

object SnapshotCodec {
    const val VERSION = 1

    /** Data Layer path of the phone's snapshot DataItem. */
    const val PATH = "/glucorag/snapshot"

    /** DataMap key holding [encode]d bytes inside that DataItem; phone and watch both use it. */
    const val DATA_KEY = "snapshot"

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    fun encode(s: Snapshot): ByteArray = json.encodeToString(Snapshot.serializer(), s).encodeToByteArray()

    /** The snapshot, or null for another version or malformed input. */
    fun decode(b: ByteArray): Snapshot? = try {
        val element = json.parseToJsonElement(b.decodeToString(throwOnInvalidSequence = true))
        if (element.jsonObject["v"]?.jsonPrimitive?.intOrNull != VERSION) {
            null
        } else {
            json.decodeFromJsonElement(Snapshot.serializer(), element)
        }
    } catch (e: IllegalArgumentException) {
        // SerializationException and non-object elements are IllegalArgumentExceptions.
        null
    } catch (e: java.nio.charset.CharacterCodingException) {
        null
    }
}
