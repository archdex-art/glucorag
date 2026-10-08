package org.glucorag.app.data

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SessionStoreTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val store by lazy {
        SessionStore(PreferenceDataStoreFactory.create(scope = scope) { tmp.root.resolve("session.preferences_pb") })
    }

    @After
    fun tearDown() = scope.cancel()

    @Test
    fun emptyUntilWritten() = runBlocking {
        assertEquals(Session(), store.current())
    }

    @Test
    fun updateRoundTripsAndNullRemoves() = runBlocking {
        val full = Session("https://g.example", "tok", "a@b.c", false, 1_759_737_600_000, "mmol/L")
        assertEquals(full, store.update { full })
        assertEquals(full, store.current())

        store.update { it.copy(token = null, lastStoredT = null) }
        assertEquals(full.copy(token = null, lastStoredT = null), store.current())
    }

    @Test
    fun localOnlyRoundTrips() = runBlocking {
        val local = Session(localOnly = true, unit = "mg/dL", lastStoredT = 7)
        store.update { local }
        assertEquals(local, store.current())
    }

    @Test
    fun clearKeepsOnlyServer() = runBlocking {
        store.update { Session("https://g.example", "tok", "a@b.c", lastStoredT = 7, unit = "mg/dL") }
        store.clear()
        assertEquals(Session(server = "https://g.example"), store.current())
    }

    @Test
    fun simulatedRoundTripsAndSignOutTurnsItOff() = runBlocking {
        store.update { Session("https://g.example", "tok", "a@b.c", simulated = true) }
        assertEquals(true, store.current().simulated)
        store.update { it.copy(simulated = false) }
        assertEquals(false, store.current().simulated)
        store.update { it.copy(simulated = true) }
        store.clear()
        assertEquals(Session(server = "https://g.example"), store.current())
    }
}
