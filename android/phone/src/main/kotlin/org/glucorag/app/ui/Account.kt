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
import org.glucorag.app.data.LocalDb
import org.glucorag.app.data.LocalProfile
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.QueuedReading
import org.glucorag.app.data.Session
import org.glucorag.app.data.SessionStore
import org.glucorag.app.forecast.OnDevice
import org.glucorag.app.forecast.Sensitivity
import org.glucorag.app.net.ApiResult
import org.glucorag.app.net.GlucoApi
import org.glucorag.app.net.ProfileIn
import org.glucorag.app.net.TokenOut
import org.glucorag.app.source.SimulatedFeed
import org.glucorag.app.source.Simulation
import org.glucorag.app.sync.SyncWorker
import org.glucorag.shared.ServerUrlCheck
import org.glucorag.shared.checkServerUrl

/**
 * The session after signing in. Switching from another account starts over; otherwise the
 * thinning marker carries on, so the phone keeps storing one reading per 5 minutes.
 */
internal fun signedIn(previous: Session, base: String, token: String, email: String, unit: String, otherAccount: Boolean): Session =
    Session(server = base, token = token, email = email, unit = unit, lastStoredT = previous.lastStoredT.takeUnless { otherAccount })

/** The session after signing out but keeping readings and About you: this phone only. */
internal fun keptOnPhone(previous: Session): Session =
    Session(localOnly = true, lastStoredT = previous.lastStoredT, unit = previous.unit, simulated = previous.simulated)

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

    /** Uses GlucoRAG without a server; returns whether About you is already filled in. */
    suspend fun useOnThisPhone(context: Context): Boolean {
        SessionStore(context).update { it.copy(localOnly = true) }
        return LocalState.get(context).profile.value != null
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
     * Stores the new device token. Replacing another signed-in account revokes its token and
     * drops its data on the phone. Coming from this phone only, the readings kept here (not
     * simulated ones) upload, and About you goes to the account if it has none.
     */
    private suspend fun finishSignIn(context: Context, base: String, out: TokenOut): Result {
        val app = context.applicationContext
        val store = SessionStore(app)
        val db = LocalDb.get(app)
        val local = LocalState.get(app)
        val previous = store.current()
        val otherAccount = previous.token != null && (previous.server != base || previous.email != out.account.email)
        if (otherAccount) {
            db.queue().clear()
            db.readings().clear()
            local.clear()
        } else {
            local.clearSync()
        }
        Simulation.cancel(app)
        store.update { signedIn(previous, base, out.token, out.account.email, out.account.unit, otherAccount) }
        if (previous.localOnly) {
            db.queue().insertAll(db.readings().all().filter { it.from != SimulatedFeed.FROM }.map { QueuedReading(it.t, it.mgdl, it.from) })
        }
        val hasProfile = shareProfile(app, base, out, previous.unit)
        SyncWorker.enqueue(app)
        if (previous.server != null && previous.token != null) revokeLater(previous.server, previous.token)
        OnDevice.run(app)
        return Result.Ok("Signed in as ${out.account.email}", hasProfile)
    }

    /**
     * The account's About you comes to the phone; without one, the phone's goes to the account
     * (in the unit chosen on the phone). Returns whether either side has one.
     */
    private suspend fun shareProfile(context: Context, base: String, out: TokenOut, phoneUnit: String?): Boolean {
        val local = LocalState.get(context)
        val api = api(base, out.token)
        val me = api.me()
        if (me !is ApiResult.Ok) return out.account.hasProfile || local.profile.value != null
        me.value.profile?.let {
            local.setProfile(LocalProfile.of(it))
            return true
        }
        val mine = local.profile.value ?: return false
        val saved = api.putProfile(mine.toProfileIn(phoneUnit ?: out.account.unit))
        if (saved is ApiResult.Ok) SessionStore(context).update { it.copy(unit = saved.value.unit) }
        // A failed upload is retried by the next sync.
        return true
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

    /**
     * Saves the About-you form: on the account first when signed in (`PUT /me/profile`), then on
     * the phone, keeping the alert sensitivity already chosen on the website. Forecasts again.
     */
    suspend fun saveProfile(context: Context, form: ProfileIn): Result {
        val app = context.applicationContext
        val store = SessionStore(app)
        val local = LocalState.get(app)
        val s = store.current()
        val existing = local.profile.value
        val sensitivity = existing?.let { Sensitivity.of(it.hypoQuantile, it.hyperQuantile) } ?: Sensitivity.STANDARD
        val body = form.copy(sensitivity = sensitivity.key)
        var unit = body.unit
        if (s.token != null && s.server != null) {
            val api = try {
                api(s.server, s.token)
            } catch (e: IllegalArgumentException) {
                return Result.Error(e.message ?: UNREACHABLE)
            }
            when (val r = api.putProfile(body)) {
                is ApiResult.Ok -> unit = r.value.unit
                ApiResult.Unauthorized -> return Result.Error("Signed out on the server. Sign in again.")
                is ApiResult.Http -> return Result.Error(r.message)
                is ApiResult.Network -> return Result.Error(UNREACHABLE)
                ApiResult.NeedsSetup -> return Result.Error("The server didn't accept these details.")
            }
            SyncWorker.enqueue(app)
        }
        local.setProfile(
            LocalProfile(
                body.age, body.gender, body.bmi, body.diabetesType,
                existing?.hypoQuantile ?: sensitivity.hypoQuantile,
                existing?.hyperQuantile ?: sensitivity.hyperQuantile,
            ),
        )
        store.update { it.copy(unit = unit) }
        OnDevice.run(app)
        return Result.Ok("Saved.")
    }

    /**
     * Revokes the token (best effort) and drops readings waiting for upload. With [keepOnPhone]
     * the phone goes on without a server, keeping its readings and About you; otherwise it
     * forgets them too.
     */
    suspend fun signOut(context: Context, keepOnPhone: Boolean) {
        val app = context.applicationContext
        val store = SessionStore(app)
        val s = store.current()
        if (s.server != null && s.token != null) {
            try {
                api(s.server, s.token).signOut()
            } catch (e: IllegalArgumentException) {
                // A stored address the rule now rejects: nothing to revoke there.
            }
        }
        WorkManager.getInstance(app).cancelUniqueWork("sync")
        val db = LocalDb.get(app)
        db.queue().clear()
        val local = LocalState.get(app)
        if (keepOnPhone) {
            store.update(::keptOnPhone)
            local.clearSync()
        } else {
            Simulation.cancel(app)
            store.clear()
            db.readings().clear()
            local.clear()
        }
    }
}
