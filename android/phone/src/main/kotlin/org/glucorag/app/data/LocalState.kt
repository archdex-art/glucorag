package org.glucorag.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.glucorag.shared.CgmReading
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec

/** How the last sync ended, for the Today screen's sync line. */
enum class SyncState { SYNCED, UNREACHABLE, SIGNED_OUT, NEEDS_SETUP }

/**
 * [at] when the last sync ended; [since] when the current state began (e.g. "unreachable since
 * 14:05"); [refused] readings the server rejected in that sync.
 */
data class SyncSummary(val state: SyncState, val at: Long, val since: Long, val refused: Int)

/**
 * What the phone knows locally, observed by the UI: the newest CGM reading received, the last
 * snapshot built (also what the watch shows), and how the last sync ended. Persisted in private
 * preferences so it survives process death; the app keeps one instance.
 */
class LocalState private constructor(private val prefs: SharedPreferences) {
    private val _reading = MutableStateFlow(loadReading())
    val reading: StateFlow<CgmReading?> = _reading.asStateFlow()

    private val _snapshot = MutableStateFlow(prefs.getString(KEY_SNAPSHOT, null)?.let { SnapshotCodec.decode(it.encodeToByteArray()) })
    val snapshot: StateFlow<Snapshot?> = _snapshot.asStateFlow()

    private val _sync = MutableStateFlow(loadSync())
    val sync: StateFlow<SyncSummary?> = _sync.asStateFlow()

    /** Keeps [r] if it is newer than the stored reading; returns whether it was. */
    @Synchronized
    fun offerReading(r: CgmReading): Boolean {
        val current = _reading.value
        if (current != null && r.t <= current.t) return false
        _reading.value = r
        prefs.edit {
            putLong(KEY_T, r.t)
            putFloat(KEY_MGDL, r.mgdl.toFloat())
            r.ratePerMin?.let { putFloat(KEY_RATE, it.toFloat()) } ?: remove(KEY_RATE)
            putString(KEY_FROM, r.from)
        }
        return true
    }

    @Synchronized
    fun setSnapshot(s: Snapshot) {
        _snapshot.value = s
        prefs.edit { putString(KEY_SNAPSHOT, SnapshotCodec.encode(s).decodeToString()) }
    }

    @Synchronized
    fun recordSync(state: SyncState, at: Long, refused: Int) {
        val previous = _sync.value
        val since = if (previous != null && previous.state == state) previous.since else at
        val summary = SyncSummary(state, at, since, refused)
        _sync.value = summary
        prefs.edit {
            putString(KEY_SYNC_STATE, state.name)
            putLong(KEY_SYNC_AT, at)
            putLong(KEY_SYNC_SINCE, since)
            putInt(KEY_SYNC_REFUSED, refused)
        }
    }

    /** Forgets everything (sign-out). */
    @Synchronized
    fun clear() {
        prefs.edit { clear() }
        _reading.value = null
        _snapshot.value = null
        _sync.value = null
    }

    private fun loadReading(): CgmReading? {
        if (!prefs.contains(KEY_T)) return null
        return CgmReading(
            t = prefs.getLong(KEY_T, 0L),
            mgdl = prefs.getFloat(KEY_MGDL, 0f).toDouble(),
            ratePerMin = if (prefs.contains(KEY_RATE)) prefs.getFloat(KEY_RATE, 0f).toDouble() else null,
            from = prefs.getString(KEY_FROM, null) ?: "",
        )
    }

    private fun loadSync(): SyncSummary? {
        val state = prefs.getString(KEY_SYNC_STATE, null)?.let { name -> SyncState.entries.firstOrNull { it.name == name } } ?: return null
        return SyncSummary(state, prefs.getLong(KEY_SYNC_AT, 0L), prefs.getLong(KEY_SYNC_SINCE, 0L), prefs.getInt(KEY_SYNC_REFUSED, 0))
    }

    companion object {
        private const val PREFS = "local_state"
        private const val KEY_T = "reading_t"
        private const val KEY_MGDL = "reading_mgdl"
        private const val KEY_RATE = "reading_rate"
        private const val KEY_FROM = "reading_from"
        private const val KEY_SNAPSHOT = "snapshot"
        private const val KEY_SYNC_STATE = "sync_state"
        private const val KEY_SYNC_AT = "sync_at"
        private const val KEY_SYNC_SINCE = "sync_since"
        private const val KEY_SYNC_REFUSED = "sync_refused"

        @Volatile
        private var instance: LocalState? = null

        fun get(context: Context): LocalState = instance ?: synchronized(this) {
            instance ?: LocalState(context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)).also { instance = it }
        }
    }
}
