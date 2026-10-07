package org.glucorag.app.net

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import java.time.Instant
import java.time.OffsetDateTime

/**
 * Mirrors of the GlucoRAG server responses (glucorag/api/auth.py, me.py, routes.py), reduced to
 * the fields the phone reads; unknown keys are ignored. Times arrive as offset-aware ISO strings
 * and are held as epoch ms; glucose is mg/dL.
 */
typealias EpochMs = @Serializable(with = IsoEpochMsSerializer::class) Long

/** Offset-aware ISO-8601 (`2026-10-06T10:00:00+02:00`, `…Z`) ⇄ epoch ms; encodes as UTC `Z`. */
object IsoEpochMsSerializer : KSerializer<Long> {
    override val descriptor = PrimitiveSerialDescriptor("org.glucorag.app.net.EpochMs", PrimitiveKind.STRING)

    override fun serialize(encoder: Encoder, value: Long) =
        encoder.encodeString(Instant.ofEpochMilli(value).toString())

    override fun deserialize(decoder: Decoder): Long =
        OffsetDateTime.parse(decoder.decodeString()).toInstant().toEpochMilli()
}

/** `GET /healthz`. */
@Serializable
data class Health(
    val status: String,
    @SerialName("model_version") val modelVersion: String,
)

/** `GET /auth/me`; [role] `person` | `clinician`, [unit] `mg/dL` | `mmol/L`. */
@Serializable
data class AccountOut(
    val email: String,
    val role: String,
    val unit: String,
    @SerialName("has_profile") val hasProfile: Boolean,
)

/** `POST /auth/token`: a long-lived bearer token for this device. */
@Serializable
data class TokenOut(
    val token: String,
    @SerialName("expires_at") val expiresAt: EpochMs,
    val account: AccountOut,
)

/** `GET /me/status`. [fresh]: the latest forecast was made from the last reading. */
@Serializable
data class StatusDto(
    val status: StatusRow,
    val prediction: PredictionDto? = null,
    val fresh: Boolean,
)

/** The patient's status row; [status] `at_risk | data_gap | warming_up | ok | no_data`. */
@Serializable
data class StatusRow(
    val status: String,
    @SerialName("last_reading") val lastReading: EpochMs? = null,
    @SerialName("last_glucose_mg_dl") val lastGlucoseMgDl: Double? = null,
    /** mg/dL per minute; null without a pair of readings one interval apart. */
    @SerialName("trend_mg_dl_per_min") val trendMgDlPerMin: Double? = null,
    val risk: List<RiskFlagDto> = emptyList(),
    /** The alert band of the latest fresh forecast; null otherwise. */
    val forecast: ForecastBandDto? = null,
)

/** [type] `hypo` | `hyper`; [severity] `low` | `medium` | `high`. */
@Serializable
data class RiskFlagDto(
    val type: String,
    @SerialName("horizon_min") val horizonMin: Int,
    val severity: String,
)

/** The forecast reduced to the patient's alert band; [horizons] in minutes after [t0]. */
@Serializable
data class ForecastBandDto(
    val t0: EpochMs,
    val horizons: List<Int>,
    val low: List<Double>,
    val median: List<Double>,
    val high: List<Double>,
)

/** The full latest forecast; [values] is `[horizon index][quantile index]`, mg/dL. */
@Serializable
data class PredictionDto(
    val t0: EpochMs,
    val horizons: List<Int>,
    val quantiles: List<Double>,
    val values: List<List<Double>>,
)

/** One stored reading from `GET /me/history`. */
@Serializable
data class ReadingDto(
    @SerialName("timestamp") val t: EpochMs,
    @SerialName("glucose_mg_dl") val mgdl: Double,
)

@Serializable
internal data class HistoryDto(val readings: List<ReadingDto>)

/** `GET /me/alerts?after_id=`; [type] `hypo | hyper | data_gap`. */
@Serializable
data class AlertDto(
    val id: Long,
    val type: String,
    val severity: String? = null,
    @SerialName("horizon_min") val horizonMin: Int? = null,
    @SerialName("t_raised") val tRaised: EpochMs,
    val t0: EpochMs? = null,
)

/** `POST /me/readings/batch`: re-sent readings count as [alreadyPresent]. */
@Serializable
data class BatchResult(
    val accepted: Int,
    @SerialName("already_present") val alreadyPresent: Int,
    val rejected: List<RejectedReading>,
)

/** [reason] `out_of_range` | `future`; [t] matches the uploaded reading's time. */
@Serializable
data class RejectedReading(
    @SerialName("timestamp") val t: EpochMs,
    val reason: String,
)

@Serializable
internal data class TokenIn(val email: String, val password: String, val device: String)

@Serializable
internal data class BatchIn(val readings: List<BatchReading>)

@Serializable
internal data class BatchReading(
    val timestamp: EpochMs,
    @SerialName("glucose_mg_dl") val glucoseMgDl: Double,
)
