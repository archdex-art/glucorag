package org.glucorag.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.core.MutablePreferences
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.io.IOException

/**
 * How the phone is set up. [localOnly]: used on this phone only, without a server. Otherwise
 * [server] is a `checkServerUrl` Ok base and [token] the device token while signed in.
 * [lastStoredT] is the newest reading kept (and queued for upload when a server is set), epoch
 * ms. [unit] is the glucose unit label: the account's as last seen on the server, or the one
 * chosen in About you on this phone only. [simulated]: the phone feeds itself simulated readings
 * (SimulatedFeed) until turned off.
 */
data class Session(
    val server: String? = null,
    val token: String? = null,
    val email: String? = null,
    val localOnly: Boolean = false,
    val lastStoredT: Long? = null,
    val unit: String? = null,
    val simulated: Boolean = false,
)

// One DataStore per file per process: the delegate holds the app's single instance. The file
// lives in app-private storage, which is excluded from backup and device transfer.
private val Context.sessionDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "session",
    corruptionHandler = ReplaceFileCorruptionHandler { emptyPreferences() },
)

/** [Session] persisted in a Preferences DataStore; a null field is stored as an absent key. */
class SessionStore(private val store: DataStore<Preferences>) {
    constructor(context: Context) : this(context.applicationContext.sessionDataStore)

    val session: Flow<Session> = store.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { it.toSession() }

    suspend fun current(): Session = session.first()

    /** Atomically replaces the session with [transform] of the stored one; returns the result. */
    suspend fun update(transform: (Session) -> Session): Session {
        var next = Session()
        store.edit { prefs ->
            next = transform(prefs.toSession())
            prefs.put(SERVER, next.server)
            prefs.put(TOKEN, next.token)
            prefs.put(EMAIL, next.email)
            prefs.put(LOCAL_ONLY, next.localOnly.takeIf { it })
            prefs.put(LAST_STORED_T, next.lastStoredT)
            prefs.put(UNIT, next.unit)
            prefs.put(SIMULATED, next.simulated.takeIf { it })
        }
        return next
    }

    /** Signs out: forgets every key except the server address. */
    suspend fun clear() {
        store.edit { prefs ->
            val server = prefs[SERVER]
            prefs.clear()
            prefs.put(SERVER, server)
        }
    }

    private companion object {
        val SERVER = stringPreferencesKey("server")
        val TOKEN = stringPreferencesKey("token")
        val EMAIL = stringPreferencesKey("email")
        val LOCAL_ONLY = booleanPreferencesKey("local_only")
        val LAST_STORED_T = longPreferencesKey("last_stored_t")
        val UNIT = stringPreferencesKey("unit")
        val SIMULATED = booleanPreferencesKey("simulated")

        fun Preferences.toSession() = Session(
            server = this[SERVER],
            token = this[TOKEN],
            email = this[EMAIL],
            localOnly = this[LOCAL_ONLY] ?: false,
            lastStoredT = this[LAST_STORED_T],
            unit = this[UNIT],
            simulated = this[SIMULATED] ?: false,
        )

        fun <T> MutablePreferences.put(key: Preferences.Key<T>, value: T?) {
            if (value == null) remove(key) else this[key] = value
        }
    }
}
