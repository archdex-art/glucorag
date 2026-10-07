package org.glucorag.app.ui

import android.content.Context
import android.os.Build
import androidx.work.WorkManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueueDb
import org.glucorag.app.data.Session
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.ApiResult
import org.glucorag.app.net.GlucoApi
import org.glucorag.app.net.ProfileIn
import org.glucorag.app.net.TokenOut
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.SyncWorker
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl

/**
 * The session after signing in: a fresh one. Alert and thinning markers start over, so the
 * first readings are never compared with another account's last queued reading.
 */
internal fun signedIn(base: String, token: String, email: String, unit: String): Session =
    Session(server = base, token = token, email = email, unit = unit)

/** Sign-in, pairing, server check, profile and sign-out, outside the UI so screens stay declarative. */
object Account {
    sealed interface Result {
        data class Ok(val message: String, val hasProfile: Boolean = true) : Result
        data class Error(val message: String) : Result
    }

    private const val UNREACHABLE =
        "Couldn't reach the server. Check the address, and that your phone is on the same network."

    /** Work that must not hold up the screen, like revoking a replaced token. */
    private val background = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private fun api(base: String, token: String? = null) = GlucoApi(base, GlucoApi.defaultClient(), { token })

    /** "Samsung SM-R890"; the server keeps it to tell your devices apart (1–64 characters). */
    private fun deviceName(): String =
        listOf(Build.MANUFACTURER.orEmpty().replaceFirstChar { it.uppercase() }, Build.MODEL.orEmpty())
            .filter { it.isNotBlank() }.distinct().joinToString(" ").take(64).ifBlank { "Android phone" }

    /** `/healthz`: "Connected to GlucoRAG shanghai-v1" or why not. */
    suspend fun checkServer(input: String): Result {
        val base = when (val check = checkServerUrl(input.trim())) {
            is ServerUrlCheck.Ok -> check.base
            is ServerUrlCheck.Rejected -> return Result.Error(check.reason)
        }
        return when (val r = api(base).health()) {
            is ApiResult.Ok -> Result.Ok("Connected to GlucoRAG ${r.value.modelVersion}")
            is ApiResult.Network -> Result.Error(UNREACHABLE)
            is ApiResult.Http -> Result.Error(r.message)
            else -> Result.Error("That address didn't answer like a GlucoRAG server.")
        }
    }

    /** Signs this phone in and stores the device token. */
    suspend fun signIn(context: Context, input: String, email: String, password: String): Result {
        val base = when (val check = checkServerUrl(input.trim())) {
            is ServerUrlCheck.Ok -> check.base
            is ServerUrlCheck.Rejected -> return Result.Error(check.reason)
        }
        return when (val r = api(base).signIn(email.trim(), password, deviceName())) {
            is ApiResult.Ok -> finishSignIn(context, base, r.value)
            ApiResult.Unauthorized -> Result.Error("Email or password is incorrect.")
            is ApiResult.Http -> Result.Error(r.message)
            is ApiResult.Network -> Result.Error(UNREACHABLE)
            ApiResult.NeedsSetup -> Result.Error("Enter your details first.")
        }
    }

    /**
     * Signs this phone in with a pairing code from the website. A code works once, so the request
     * isn't cancelled when the screen goes away: the token it returns must be kept.
     */
    suspend fun pair(context: Context, link: PairLink.Ok): Result = withContext(NonCancellable) {
        when (val r = api(link.server).pair(link.code, deviceName())) {
            is ApiResult.Ok -> finishSignIn(context, link.server, r.value)
            is ApiResult.Http -> Result.Error(r.message)
            is ApiResult.Network -> Result.Error(UNREACHABLE)
            ApiResult.Unauthorized, ApiResult.NeedsSetup -> Result.Error("That address didn't answer like a GlucoRAG server.")
        }
    }

    /**
     * Stores the new device token. Replacing a signed-in account (pairing while signed in) revokes
     * the old token, and drops readings still waiting for the old account.
     */
    private suspend fun finishSignIn(context: Context, base: String, out: TokenOut): Result {
        val app = context.applicationContext
        val store = SessionStore(app)
        val previous = store.current()
        val otherAccount = previous.token != null && (previous.server != base || previous.email != out.account.email)
        if (otherAccount) QueueDb.get(app).queue().clear()
        Simulation.cancel(app)
        store.update { signedIn(base, out.token, out.account.email, out.account.unit) }
        LocalState.get(app).clear()
        SyncWorker.enqueue(app)
        if (previous.server != null && previous.token != null) revokeLater(previous.server, previous.token)
        return Result.Ok("Signed in as ${out.account.email}", out.account.hasProfile)
    }

    private fun revokeLater(server: String, token: String) {
        background.launch {
            try {
                api(server, token).signOut()
            } catch (e: IllegalArgumentException) {
                // A stored address the rule now rejects: nothing to revoke there.
            }
        }
    }

    /** Saves the About-you form (`PUT /me/profile`) and the unit it chose. */
    suspend fun saveProfile(context: Context, profile: ProfileIn): Result {
        val store = SessionStore(context)
        val s = store.current()
        val base = s.server ?: return Result.Error("Sign in first.")
        val api = try {
            api(base, s.token)
        } catch (e: IllegalArgumentException) {
            return Result.Error(e.message ?: UNREACHABLE)
        }
        return when (val r = api.putProfile(profile)) {
            is ApiResult.Ok -> {
                store.update { it.copy(unit = r.value.unit) }
                SyncWorker.enqueue(context)
                Result.Ok("Saved.")
            }
            ApiResult.Unauthorized -> Result.Error("Signed out on the server. Sign in again.")
            is ApiResult.Http -> Result.Error(r.message)
            is ApiResult.Network -> Result.Error(UNREACHABLE)
            ApiResult.NeedsSetup -> Result.Error("The server didn't accept these details.")
        }
    }

    /** Revokes the token (best effort), drops waiting readings and forgets local state. */
    suspend fun signOut(context: Context) {
        val store = SessionStore(context)
        val s = store.current()
        if (s.server != null && s.token != null) {
            try {
                api(s.server, s.token).signOut()
            } catch (e: IllegalArgumentException) {
                // A stored address the rule now rejects: nothing to revoke there.
            }
        }
        WorkManager.getInstance(context).cancelUniqueWork("sync")
        Simulation.cancel(context)
        QueueDb.get(context).queue().clear()
        store.clear()
        LocalState.get(context).clear()
    }
}
