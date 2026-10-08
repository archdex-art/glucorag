package org.glucorag.app.sync

import org.glucorag.app.data.LocalProfile
import org.glucorag.app.data.QueueDao
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.ApiResult
import org.glucorag.app.net.GlucoApi
import org.glucorag.shared.CgmReading

/** What one sync achieved. The forecast and alerts don't depend on it: the phone makes them. */
sealed interface SyncOutcome {
    /** [uploaded] readings left the queue; [refused] of them the server rejected (time, range). */
    data class Synced(val uploaded: Int, val refused: Int, val profileChanged: Boolean) : SyncOutcome

    /** The token was revoked or expired: uploads stop, the queue is kept for the next sign-in. */
    data object SignedOut : SyncOutcome

    /** Neither the account nor this phone has About you yet. */
    data object NeedsSetup : SyncOutcome

    /** The server could not be reached or failed; try again later. */
    data class Retry(val reason: String) : SyncOutcome
}

/**
 * One sync with the server: take the account's unit and profile (About you entered on the
 * website reaches the phone's forecast), or give the account this phone's profile when it has
 * none, then drain the upload queue. Pure Kotlin over [GlucoApi], [QueueDao] and [SessionStore],
 * so it runs on the JVM in tests.
 */
class SyncEngine(
    private val api: GlucoApi,
    private val queue: QueueDao,
    private val store: SessionStore,
    private val localProfile: () -> LocalProfile?,
    private val saveProfile: (LocalProfile) -> Unit,
) {
    /** A failed API call, carried out of the happy path. */
    private class Stop(val result: ApiResult<Nothing>) : Exception(null, null, false, false)

    suspend fun run(): SyncOutcome {
        var uploaded = 0
        var refused = 0
        return try {
            val account = ok(api.account())
            store.update { it.copy(unit = account.unit) }
            val local = localProfile()
            val remote = ok(api.me()).profile
            var changed = false
            if (remote != null) {
                val p = LocalProfile.of(remote)
                if (p != local) {
                    saveProfile(p)
                    changed = true
                }
            } else {
                if (local == null) return SyncOutcome.NeedsSetup
                ok(api.putProfile(local.toProfileIn(account.unit)))
            }
            // Re-read the queue after every batch: readings queued during the upload are sent too.
            while (true) {
                val batch = queue.oldest(BATCH_SIZE)
                if (batch.isEmpty()) break
                val result = ok(api.uploadBatch(batch.map { CgmReading(it.t, it.mgdl, null, it.from) }))
                queue.deleteByT(batch.map { it.t })
                uploaded += batch.size
                refused += result.rejected.size
            }
            SyncOutcome.Synced(uploaded, refused, changed)
        } catch (stop: Stop) {
            when (val r = stop.result) {
                ApiResult.Unauthorized -> SyncOutcome.SignedOut
                ApiResult.NeedsSetup -> SyncOutcome.NeedsSetup
                is ApiResult.Network -> SyncOutcome.Retry(r.cause.message ?: "network")
                is ApiResult.Http -> SyncOutcome.Retry("HTTP ${r.code}: ${r.message}")
                is ApiResult.Ok -> error("unreachable")
            }
        }
    }

    private fun <T> ok(result: ApiResult<T>): T = when (result) {
        is ApiResult.Ok -> result.value
        ApiResult.Unauthorized -> throw Stop(ApiResult.Unauthorized)
        ApiResult.NeedsSetup -> throw Stop(ApiResult.NeedsSetup)
        is ApiResult.Http -> throw Stop(result)
        is ApiResult.Network -> throw Stop(result)
    }

    companion object {
        const val BATCH_SIZE = 500
    }
}
