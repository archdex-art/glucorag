package org.glucorag.wear.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec

private val Context.snapshotDataStore: DataStore<Preferences> by preferencesDataStore(name = "snapshot")

/** The latest snapshot from the phone, kept as its JSON bytes. */
class SnapshotStore(context: Context) {
    private val store = context.applicationContext.snapshotDataStore

    val flow: Flow<Snapshot?> = store.data
        .map { it[KEY] }
        .distinctUntilChanged()
        .map { json -> json?.let { SnapshotCodec.decode(it.encodeToByteArray()) } }

    suspend fun latest(): Snapshot? = flow.first()

    /**
     * Decodes [bytes] and persists them only if the snapshot is newer (`written`) than the stored
     * one. Returns the saved snapshot, or null when the bytes are invalid or not newer.
     */
    suspend fun save(bytes: ByteArray): Snapshot? {
        val snapshot = SnapshotCodec.decode(bytes) ?: return null
        var saved = false
        store.edit { prefs ->
            val current = prefs[KEY]?.let { SnapshotCodec.decode(it.encodeToByteArray()) }
            if (current == null || snapshot.written > current.written) {
                prefs[KEY] = bytes.decodeToString()
                saved = true
            }
        }
        return if (saved) snapshot else null
    }

    private companion object {
        val KEY = stringPreferencesKey("snapshot_json")
    }
}
