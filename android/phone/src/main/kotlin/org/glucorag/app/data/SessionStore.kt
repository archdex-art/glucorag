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
 * The signed-in phone's state. [server] is a `checkServerUrl` Ok base; [lastAlertId] is the
 * newest alert already handled (null until the first sync after sign-in); [lastQueuedT] is the
 * newest reading queued for upload, epoch ms. [unit] is the account's glucose unit label as last
 * seen on the server; [notifiedAlerts] holds the `type@t_raised` keys of the most recent alert
 * notifications, oldest first, so an alert the server re-raises with a new id doesn't buzz twice.
 * [simulated]: the phone feeds itself simulated readings (SimulatedFeed) until turned off.
 */
data class Session(
    val server: String? = null,
    val token: String? = null,
    val email: String? = null,
    val lastAlertId: Long? = null,
    val lastQueuedT: Long? = null,
    val unit: String? = null,
    val notifiedAlerts: List<String> = emptyList(),
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
            prefs.put(LAST_ALERT_ID, next.lastAlertId)
            prefs.put(LAST_QUEUED_T, next.lastQueuedT)
            prefs.put(UNIT, next.unit)
            prefs.put(NOTIFIED_ALERTS, next.notifiedAlerts.takeIf { it.isNotEmpty() }?.joinToString("\n"))
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
        val LAST_ALERT_ID = longPreferencesKey("last_alert_id")
        val LAST_QUEUED_T = longPreferencesKey("last_queued_t")
        val UNIT = stringPreferencesKey("unit")
        val NOTIFIED_ALERTS = stringPreferencesKey("notified_alerts")
        val SIMULATED = booleanPreferencesKey("simulated")

        fun Preferences.toSession() = Session(
            server = this[SERVER],
            token = this[TOKEN],
            email = this[EMAIL],
            lastAlertId = this[LAST_ALERT_ID],
            lastQueuedT = this[LAST_QUEUED_T],
            unit = this[UNIT],
            notifiedAlerts = this[NOTIFIED_ALERTS]?.split("\n")?.filter { it.isNotEmpty() } ?: emptyList(),
            simulated = this[SIMULATED] ?: false,
        )

        fun <T> MutablePreferences.put(key: Preferences.Key<T>, value: T?) {
            if (value == null) remove(key) else this[key] = value
        }
    }
}
