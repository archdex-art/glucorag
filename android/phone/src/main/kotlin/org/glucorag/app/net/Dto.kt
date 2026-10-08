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

/**
 * `GET /me`, reduced to the profile: the four facts the model reads and the alert quantiles the
 * account's sensitivity selects; null until the account has one.
 */
@Serializable
data class MeOut(val profile: ProfileOut? = null)

@Serializable
data class ProfileOut(
    val age: Int,
    val gender: String,
    val bmi: Double,
    @SerialName("diabetes_type") val diabetesType: String,
    @SerialName("hypo_quantile") val hypoQuantile: Double,
    @SerialName("hyper_quantile") val hyperQuantile: Double,
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

/** `POST /auth/pair`: a one-time code from the website instead of a password. */
@Serializable
internal data class PairIn(val code: String, val device: String)

/**
 * `PUT /me/profile`: [gender] `F` | `M`, [diabetesType] `T1D` | `T2D`, [sensitivity]
 * `standard` | `cautious` | `very_cautious`, [unit] `mg/dL` | `mmol/L`.
 */
@Serializable
data class ProfileIn(
    val age: Int,
    val gender: String,
    val bmi: Double,
    @SerialName("diabetes_type") val diabetesType: String,
    val sensitivity: String,
    val unit: String,
)

/** The account `PUT /me/profile` answers with, reduced to the unit it now shows. */
@Serializable
data class ProfileSaved(val unit: String)

@Serializable
internal data class BatchIn(val readings: List<BatchReading>)

@Serializable
internal data class BatchReading(
    val timestamp: EpochMs,
    @SerialName("glucose_mg_dl") val glucoseMgDl: Double,
)
