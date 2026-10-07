package org.glucorag.wear.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

/** The one-time research-prototype acknowledgement. */
class AcknowledgementStore(context: Context) {
    private val store = context.applicationContext.settingsDataStore

    val acknowledged: Flow<Boolean> = store.data.map { it[KEY] ?: false }

    suspend fun acknowledge() {
        store.edit { it[KEY] = true }
    }

    private companion object {
        val KEY = booleanPreferencesKey("acknowledged")
    }
}
