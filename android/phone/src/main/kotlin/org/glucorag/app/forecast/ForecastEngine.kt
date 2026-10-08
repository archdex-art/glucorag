package org.glucorag.app.forecast

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.glucorag.shared.CgmReading
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import kotlin.math.floor

/**
 * `assets/model/meta.json`, written by `glucorag-export-onnx` next to `model.onnx`: what the
 * phone needs besides the graph to reproduce the server's `ForecastEngine.predict`.
 */
@Serializable
data class DeviceMeta(
    val version: String,
    @SerialName("interval_min") val intervalMin: Int,
    @SerialName("lookback_steps") val lookbackSteps: Int,
    @SerialName("horizon_steps") val horizonSteps: Int,
    @SerialName("max_gap_min") val maxGapMin: Int,
    @SerialName("pad_slots") val padSlots: Int,
    val quantiles: List<Double>,
    @SerialName("glucose_norm") val glucoseNorm: Norm,
    @SerialName("sensor_range_mg_dl") val sensorRange: List<Double>,
    @SerialName("static_encoder") val staticEncoder: StaticEncoder,
    val inputs: List<String>,
    val output: String,
) {
    @Serializable
    data class Norm(val mu: Double, val sigma: Double)

    /** Feature i of the static input: a categorical code, or z-normalized with its statistics. */
    @Serializable
    data class StaticEncoder(
        val features: List<String>,
        val categorical: Map<String, Map<String, Double>>,
        val continuous: Map<String, Norm>,
    )

    val horizonsMin: List<Int> get() = (1..horizonSteps).map { it * intervalMin }

    /** Minutes of history the server's window buffer keeps (look-back, one gap, two trend points). */
    val historySpanMin: Int get() = lookbackSteps * intervalMin + maxGapMin + 2 * intervalMin

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        fun parse(text: String): DeviceMeta = json.decodeFromString(serializer(), text)
    }
}

/** The look-back window has a gap longer than the imputation limit (or no readings at all). */
class DataGapException(message: String) : Exception(message)

/** The model inputs for one forecast; [t0] is the newest reading's time, epoch ms. */
class ModelInputs(val xEnc: Array<FloatArray>, val xDec: FloatArray, val t0: Long)

/** A quantile forecast in mg/dL: [values] is `[horizon index][quantile index]`, sorted per horizon. */
class QuantileForecast(
    val t0: Long,
    val horizons: List<Int>,
    val quantiles: List<Double>,
    val values: List<DoubleArray>,
) {
    fun column(q: Double): List<Double> {
        val i = quantileIndex(quantiles, q)
        return values.map { it[i] }
    }
}

/** Index of [q] in the model's quantiles; an unknown level is a configuration error. */
fun quantileIndex(quantiles: List<Double>, q: Double): Int =
    quantiles.indexOfFirst { kotlin.math.abs(it - q) < 1e-9 }.takeIf { it >= 0 }
        ?: throw IllegalArgumentException("Quantile $q is not produced by the model (has $quantiles)")

/** The exported network: static (S), x_enc (L × 2), x_dec (H) → normalized quantiles (H × Q). */
fun interface QuantileModel {
    fun run(static: FloatArray, xEnc: Array<FloatArray>, xDec: FloatArray): Array<FloatArray>
}

/**
 * The server's `glucorag.inference.engine.ForecastEngine` on the phone: the same input grid,
 * causal gap filling, normalization and post-processing around the exported network. Times are
 * read as local wall-clock time in the given zone, the frame the server stores readings in.
 */
class ForecastEngine(val meta: DeviceMeta, private val model: QuantileModel) {
    private val stepMs = meta.intervalMin * MINUTE_MS
    private val maxGapSteps = meta.maxGapMin / meta.intervalMin

    /** `StaticEncoder.encode_one`: [features] maps `gender`, `age`, `bmi`, `diabetes_type`. */
    fun encodeStatic(features: Map<String, Any>): FloatArray {
        val enc = meta.staticEncoder
        return FloatArray(enc.features.size) { i ->
            val f = enc.features[i]
            val value = features[f] ?: throw IllegalArgumentException("Profile is missing static feature '$f'")
            val codes = enc.categorical[f]
            if (codes != null) {
                (codes[value.toString()] ?: throw IllegalArgumentException("Invalid $f=$value; expected one of ${codes.keys}")).toFloat()
            } else {
                val norm = enc.continuous.getValue(f)
                ((toDouble(value) - norm.mu) / norm.sigma).toFloat()
            }
        }
    }

    /**
     * `build_inputs`: each grid slot keeps the reading nearest its time within half a step
     * (ties go to the later reading; a reading exactly half a step between two slots fills only
     * the newer), gaps up to the imputation limit are filled by causal linear extrapolation, then
     * glucose is z-normalized and times become time of day in [0, 1).
     */
    fun buildInputs(history: List<CgmReading>, zone: ZoneId): ModelInputs {
        if (history.isEmpty()) throw DataGapException("No CGM readings")
        // Python sorts naive wall times; sortedBy is stable like its sorted().
        val readings = history.map { WallReading(wallMs(it.t, zone), it.mgdl, it.t) }.sortedBy { it.wall }
        val newest = readings.last()
        val t0 = newest.wall
        val nSlots = meta.lookbackSteps + meta.padSlots + maxGapSteps
        val grid = DoubleArray(nSlots) { Double.NaN }
        val best = DoubleArray(nSlots) { Double.POSITIVE_INFINITY }
        val stepS = stepMs / 1000.0
        val halfStep = stepS / 2
        for (r in readings) {
            val ageS = (t0 - r.wall) / 1000.0
            val lo = floor(ageS / stepS)
            val newerOff = ageS - lo * stepS
            val olderOff = (lo + 1) * stepS - ageS
            val (k, offset) = if (newerOff <= halfStep) lo to newerOff else (lo + 1) to olderOff
            if (k >= 0 && k < nSlots) {
                val slot = nSlots - 1 - k.toInt()
                if (offset <= best[slot]) {
                    best[slot] = offset
                    grid[slot] = r.mgdl
                }
            }
        }
        val filled = causalLinearExtrapolate(grid, maxGapSteps, meta.sensorRange[0], meta.sensorRange[1])
            .copyOfRange(nSlots - meta.lookbackSteps, nSlots)
        if (filled.any { it.isNaN() }) {
            throw DataGapException("Gap > ${maxGapSteps * meta.intervalMin} min in look-back window")
        }
        val norm = meta.glucoseNorm
        val xEnc = Array(meta.lookbackSteps) { i ->
            val k = meta.lookbackSteps - 1 - i
            floatArrayOf(((filled[i] - norm.mu) / norm.sigma).toFloat(), timeNorm(t0 - stepMs * k).toFloat())
        }
        val xDec = FloatArray(meta.horizonSteps) { k -> timeNorm(t0 + stepMs * (k + 1)).toFloat() }
        return ModelInputs(xEnc, xDec, newest.t)
    }

    /** `predict`: quantiles in mg/dL, sorted per horizon (the heads can cross) and clipped. */
    fun predict(features: Map<String, Any>, history: List<CgmReading>, zone: ZoneId): QuantileForecast {
        val inputs = buildInputs(history, zone)
        val out = model.run(encodeStatic(features), inputs.xEnc, inputs.xDec)
        val norm = meta.glucoseNorm
        val (min, max) = meta.sensorRange
        val values = out.map { row ->
            val mg = DoubleArray(row.size) { q -> row[q].toDouble() * norm.sigma + norm.mu }
            mg.sort()
            DoubleArray(mg.size) { q -> mg[q].coerceIn(min, max) }
        }
        return QuantileForecast(inputs.t0, meta.horizonsMin, meta.quantiles, values)
    }

    private class WallReading(val wall: Long, val mgdl: Double, val t: Long)

    companion object {
        private const val MINUTE_MS = 60_000L

        /** [t] (epoch ms) as naive local wall-clock ms: what the server's naive datetimes hold. */
        fun wallMs(t: Long, zone: ZoneId): Long =
            t + zone.rules.getOffset(Instant.ofEpochMilli(t)).totalSeconds * 1000L

        /** `_time_norm`: (hour·60 + minute + second/60) / 1440 of a wall time; sub-seconds ignored. */
        fun timeNorm(wall: Long): Double {
            val t = LocalDateTime.ofEpochSecond(Math.floorDiv(wall, 1000L), 0, ZoneOffset.UTC)
            return (t.hour * 60 + t.minute + t.second / 60.0) / 1440.0
        }

        private fun toDouble(value: Any): Double = when (value) {
            is Number -> value.toDouble()
            else -> value.toString().toDouble()
        }
    }
}

/**
 * `glucorag.preprocess.impute.causal_linear_extrapolate`: fills NaN runs of at most
 * [maxGapSteps] by continuing the line through the two most recent observed points (flat with
 * one, none with zero); longer runs stay NaN. Every value is clipped to [[min], [max]].
 */
fun causalLinearExtrapolate(values: DoubleArray, maxGapSteps: Int, min: Double, max: Double): DoubleArray {
    val filled = values.copyOf()
    var lastI = -1
    var prevI = -1
    var i = 0
    val n = values.size
    while (i < n) {
        if (!values[i].isNaN()) {
            prevI = lastI
            lastI = i
            i++
            continue
        }
        var gapEnd = i
        while (gapEnd < n && values[gapEnd].isNaN()) gapEnd++
        if (lastI >= 0 && gapEnd - i <= maxGapSteps) {
            val slope = if (prevI >= 0) (values[lastI] - values[prevI]) / (lastI - prevI) else 0.0
            for (j in i until gapEnd) filled[j] = values[lastI] + slope * (j - lastI)
        }
        i = gapEnd
    }
    for (j in filled.indices) if (!filled[j].isNaN()) filled[j] = filled[j].coerceIn(min, max)
    return filled
}
