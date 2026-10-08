package org.glucorag.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import org.glucorag.app.forecast.Sensitivity
import org.glucorag.app.net.ProfileIn
import org.glucorag.app.net.ProfileOut

/**
 * About you, kept on the phone: the four facts the model reads and the alert quantiles. In
 * connected mode it mirrors the account's profile (`GET /me`); on this phone only it is the sole copy.
 */
@Serializable
data class LocalProfile(
    val age: Int,
    val gender: String,
    val bmi: Double,
    @SerialName("diabetes_type") val diabetesType: String,
    @SerialName("hypo_quantile") val hypoQuantile: Double = Sensitivity.STANDARD.hypoQuantile,
    @SerialName("hyper_quantile") val hyperQuantile: Double = Sensitivity.STANDARD.hyperQuantile,
) {
    /** The static features by the names the model's encoder uses. */
    fun features(): Map<String, Any> = mapOf("gender" to gender, "age" to age, "bmi" to bmi, "diabetes_type" to diabetesType)

    /** The `PUT /me/profile` body; a custom quantile pair (set by staff) is sent as `standard`. */
    fun toProfileIn(unit: String): ProfileIn = ProfileIn(
        age = age,
        gender = gender,
        bmi = bmi,
        diabetesType = diabetesType,
        sensitivity = (Sensitivity.of(hypoQuantile, hyperQuantile) ?: Sensitivity.STANDARD).key,
        unit = unit,
    )

    companion object {
        /** The account's profile as the server stores it. */
        fun of(p: ProfileOut): LocalProfile =
            LocalProfile(p.age, p.gender, p.bmi, p.diabetesType, p.hypoQuantile, p.hyperQuantile)
    }
}
