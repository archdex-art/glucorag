package org.glucorag.app.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.glucorag.shared.CgmReading
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl
import java.io.IOException
import java.time.DateTimeException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** The outcome of one API call; failures never throw. */
sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>

    /** 401: the token is missing, expired or revoked, or (on sign-in) the credentials are wrong. */
    data object Unauthorized : ApiResult<Nothing>

    /** 409: the account has no profile yet. */
    data object NeedsSetup : ApiResult<Nothing>

    /** Any other failure the server answered; [message] is its `detail` when it gave one. */
    data class Http(val code: Int, val message: String) : ApiResult<Nothing>

    /** No answer: connection refused, DNS, TLS, timeout. */
    data class Network(val cause: Throwable) : ApiResult<Nothing>
}

/**
 * The GlucoRAG server API for a signed-in phone. [base] must pass `checkServerUrl` (so the bearer
 * token never goes to a cleartext public host); a Rejected address throws IllegalArgumentException.
 * [token] is read per request and sent as `Authorization: Bearer` when present.
 */
class GlucoApi(base: String, private val client: OkHttpClient, private val token: () -> String?) {
    private val base: HttpUrl = when (val check = checkServerUrl(base)) {
        is ServerUrlCheck.Ok -> check.base.toHttpUrl()
        is ServerUrlCheck.Rejected -> throw IllegalArgumentException(check.reason)
    }

    suspend fun health(): ApiResult<Health> = get("healthz", Health.serializer())

    /** Sign this device in; the request never carries a previous token. */
    suspend fun signIn(email: String, password: String, device: String): ApiResult<TokenOut> =
        call(
            Request.Builder().url(url("auth/token")).post(jsonBody(TokenIn.serializer(), TokenIn(email, password, device))),
            TokenOut.serializer(),
            authorize = false,
        )

    /**
     * Sign this device in with a one-time pairing code from the website. A refused code is
     * [ApiResult.Http] 401 carrying the server's explanation, not [ApiResult.Unauthorized].
     */
    suspend fun pair(code: String, device: String): ApiResult<TokenOut> =
        call(
            Request.Builder().url(url("auth/pair")).post(jsonBody(PairIn.serializer(), PairIn(code, device))),
            TokenOut.serializer(),
            authorize = false,
            detailOn401 = true,
        )

    suspend fun account(): ApiResult<AccountOut> = get("auth/me", AccountOut.serializer())

    /** Saves the four facts the forecast needs and the display unit. */
    suspend fun putProfile(profile: ProfileIn): ApiResult<ProfileSaved> =
        call(Request.Builder().url(url("me/profile")).put(jsonBody(ProfileIn.serializer(), profile)), ProfileSaved.serializer())

    /** The account's profile, if it has one. */
    suspend fun me(): ApiResult<MeOut> = get("me", MeOut.serializer())

    /** Times are sent as UTC ISO-8601 (`2026-10-06T08:00:00Z`). */
    suspend fun uploadBatch(readings: List<CgmReading>): ApiResult<BatchResult> {
        val body = BatchIn(readings.map { BatchReading(it.t, it.mgdl) })
        return call(
            Request.Builder().url(url("me/readings/batch")).post(jsonBody(BatchIn.serializer(), body)),
            BatchResult.serializer(),
        )
    }

    /** Revokes this device's token on the server (`POST /auth/logout`, 204). */
    suspend fun signOut(): ApiResult<Unit> =
        call(Request.Builder().url(url("auth/logout")).post(ByteArray(0).toRequestBody()), Unit.serializer(), noContent = Unit)

    private fun url(path: String, vararg query: Pair<String, String>): HttpUrl =
        base.newBuilder().addPathSegments(path).apply {
            query.forEach { (k, v) -> addQueryParameter(k, v) }
        }.build()

    private fun <T> jsonBody(serializer: KSerializer<T>, value: T): RequestBody =
        json.encodeToString(serializer, value).toRequestBody(JSON_TYPE)

    private suspend fun <T> get(path: String, serializer: KSerializer<T>, vararg query: Pair<String, String>) =
        call(Request.Builder().url(url(path, *query)).get(), serializer)

    /**
     * [noContent], when given, is the result of a successful reply with an empty body (204).
     * [detailOn401]: a 401 is [ApiResult.Http] with the server's `detail` (a refused code, not a lost token).
     */
    private suspend fun <T> call(
        builder: Request.Builder,
        serializer: KSerializer<T>,
        authorize: Boolean = true,
        noContent: T? = null,
        detailOn401: Boolean = false,
    ): ApiResult<T> {
        if (authorize) token()?.takeIf { it.isNotBlank() }?.let { builder.header("Authorization", "Bearer $it") }
        return try {
            client.newCall(builder.build()).await().use { response ->
                val text = withContext(Dispatchers.IO) { response.body.string() }
                when {
                    response.isSuccessful && noContent != null && text.isBlank() -> ApiResult.Ok(noContent)
                    response.isSuccessful -> try {
                        ApiResult.Ok(json.decodeFromString(serializer, text))
                    } catch (e: IllegalArgumentException) {
                        // SerializationException (malformed or wrong-shaped JSON) is one too.
                        ApiResult.Http(response.code, UNREADABLE)
                    } catch (e: DateTimeException) {
                        ApiResult.Http(response.code, UNREADABLE)
                    }
                    response.code == 401 && !detailOn401 -> ApiResult.Unauthorized
                    response.code == 409 -> ApiResult.NeedsSetup
                    else -> ApiResult.Http(
                        response.code,
                        detailOf(text) ?: "The server answered with error ${response.code}.",
                    )
                }
            }
        } catch (e: IOException) {
            ApiResult.Network(e)
        }
    }

    companion object {
        private val JSON_TYPE = "application/json".toMediaType()

        private const val UNREADABLE = "The server's answer wasn't understood."
        private val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
        }

        /** The client the app uses: 15 s to connect, 30 s to read. */
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()

        /** FastAPI's string `detail`; validation errors (a list) and non-JSON bodies give null. */
        private fun detailOf(text: String): String? = try {
            ((json.parseToJsonElement(text) as? JsonObject)?.get("detail") as? JsonPrimitive)
                ?.takeIf { it.isString }?.content?.takeIf { it.isNotBlank() }
        } catch (e: SerializationException) {
            null
        }
    }
}

/** Runs the call on OkHttp's dispatcher; cancelling the coroutine cancels the call. */
private suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    cont.invokeOnCancellation { cancel() }
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) {
            cont.resume(response) { _, value, _ -> value.close() }
        }

        override fun onFailure(call: Call, e: IOException) {
            cont.resumeWithException(e)
        }
    })
}
