package org.glucorag.app.ui

import android.content.Context
import android.os.Build
import androidx.work.WorkManager
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueueDb
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.ApiResult
import org.glucorag.app.net.GlucoApi
import org.glucorag.app.sync.SyncWorker
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl

/** Sign-in, server check and sign-out, outside the UI so screens stay declarative. */
object Account {
    sealed interface Result {
        data class Ok(val message: String, val hasProfile: Boolean = true) : Result
        data class Error(val message: String) : Result
    }

    private const val UNREACHABLE =
        "Couldn't reach the server. Check the address, and that your phone is on the same network."

    private fun api(base: String, token: String? = null) = GlucoApi(base, GlucoApi.defaultClient(), { token })

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
        val device = listOf(Build.MANUFACTURER.replaceFirstChar { it.uppercase() }, Build.MODEL).distinct().joinToString(" ").take(64)
        return when (val r = api(base).signIn(email.trim(), password, device)) {
            is ApiResult.Ok -> {
                val out = r.value
                SessionStore(context).update {
                    it.copy(server = base, token = out.token, email = out.account.email, unit = out.account.unit, lastAlertId = null)
                }
                LocalState.get(context).clear()
                SyncWorker.enqueue(context)
                Result.Ok("Signed in as ${out.account.email}", out.account.hasProfile)
            }
            ApiResult.Unauthorized -> Result.Error("Email or password is incorrect.")
            is ApiResult.Http -> Result.Error(r.message)
            is ApiResult.Network -> Result.Error(UNREACHABLE)
            ApiResult.NeedsSetup -> Result.Error("Finish setup on the website.")
        }
    }

    /** Re-reads the account (after finishing setup on the website). */
    suspend fun hasProfile(context: Context): Boolean? {
        val s = SessionStore(context).current()
        val base = s.server ?: return null
        return (api(base, s.token).account() as? ApiResult.Ok)?.value?.hasProfile
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
        QueueDb.get(context).queue().clear()
        store.clear()
        LocalState.get(context).clear()
    }
}
