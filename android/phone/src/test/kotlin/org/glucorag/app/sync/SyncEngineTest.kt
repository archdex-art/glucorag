package org.glucorag.app.sync

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.runBlocking
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.glucorag.app.data.LocalProfile
import org.glucorag.app.data.QueueDao
import org.glucorag.app.data.QueuedReading
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.GlucoApi
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.net.InetAddress
import java.util.concurrent.CopyOnWriteArrayList

class SyncEngineTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val server = MockWebServer()
    private val requests = CopyOnWriteArrayList<RecordedRequest>()

    /** 2026-10-06T08:00:00Z. */
    private val now = 1_759_737_600_000L
    private val min = 60_000L

    private lateinit var store: SessionStore
    private val queue = FakeQueue()
    private var phoneProfile: LocalProfile? = null

    // Server-side state the dispatcher serves.
    private var unit = "mg/dL"
    private var accountProfile: String? = """{"age":41,"gender":"F","bmi":23.4,"diabetes_type":"T1D","sensitivity":"cautious","hypo_quantile":0.1,"hyper_quantile":0.9}"""
    private var batchStatus = 200
    private var rejectAll = false

    @Before
    fun setUp() {
        store = SessionStore(PreferenceDataStoreFactory.create(scope = scope) { tmp.root.resolve("s.preferences_pb") })
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                requests += request
                val path = request.url.encodedPath
                return when {
                    path == "/me/readings/batch" -> if (batchStatus != 200) json("""{"detail":"x"}""", batchStatus) else {
                        val n = Regex("\"timestamp\"").findAll(request.body?.utf8() ?: "").count()
                        if (rejectAll) json("""{"accepted":0,"already_present":0,"rejected":[]}""") else json("""{"accepted":$n,"already_present":0,"rejected":[]}""")
                    }
                    path == "/auth/me" -> json("""{"email":"a@example.com","role":"person","unit":"$unit","has_profile":${accountProfile != null}}""")
                    path == "/me" -> json("""{"email":"a@example.com","role":"person","unit":"$unit","profile":${accountProfile ?: "null"}}""")
                    path == "/me/profile" && request.method == "PUT" -> json("""{"unit":"mmol/L"}""")
                    else -> json("""{"detail":"not found"}""", 404)
                }
            }
        }
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        runBlocking { store.update { it.copy(server = base(), token = "tok") } }
    }

    @After
    fun tearDown() {
        server.close()
        scope.cancel()
    }

    private fun base() = "http://127.0.0.1:${server.port}"

    private fun json(body: String, code: Int = 200) =
        MockResponse.Builder().code(code).setHeader("Content-Type", "application/json").body(body).build()

    private fun engine(base: String = base()) = SyncEngine(
        api = GlucoApi(base, OkHttpClient(), { "tok" }),
        queue = queue,
        store = store,
        localProfile = { phoneProfile },
        saveProfile = { phoneProfile = it },
    )

    private fun batchRequests() = requests.filter { it.url.encodedPath == "/me/readings/batch" }

    @Test
    fun drainsBacklogInBatchesOf500() = runBlocking {
        repeat(1_200) { i -> queue.insert(QueuedReading(now - (1_200 - i) * 5 * min, 120.0, "juggluco")) }
        val outcome = engine().run()
        val batches = batchRequests()
        assertEquals(3, batches.size)
        val firstTimes = batches.map { Regex("\"timestamp\":\"([^\"]+)\"").find(it.body!!.utf8())!!.groupValues[1] }
        assertEquals(firstTimes.sorted(), firstTimes)
        assertEquals(0, queue.count())
        assertEquals(1_200, (outcome as SyncOutcome.Synced).uploaded)
    }

    @Test
    fun rejectedReadingsLeaveQueue() = runBlocking {
        rejectAll = true
        queue.insert(QueuedReading(now + 10 * min, 120.0, "juggluco"))
        engine().run()
        assertEquals(0, queue.count())
    }

    @Test
    fun unauthorizedKeepsQueueAndSignsOut() = runBlocking {
        batchStatus = 401
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        assertEquals(SyncOutcome.SignedOut, engine().run())
        assertEquals(1, queue.count())
    }

    @Test
    fun networkFailureKeepsQueueForRetry() = runBlocking {
        val closed = base()
        server.close()
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        assertTrue(engine(base = closed).run() is SyncOutcome.Retry)
        assertEquals(1, queue.count())
    }

    @Test
    fun theAccountsProfileAndUnitReachThePhone() = runBlocking {
        unit = "mmol/L"
        phoneProfile = LocalProfile(30, "M", 25.0, "T2D")
        val outcome = engine().run() as SyncOutcome.Synced
        assertTrue(outcome.profileChanged)
        assertEquals(LocalProfile(41, "F", 23.4, "T1D", 0.1, 0.9), phoneProfile)
        assertEquals("mmol/L", store.current().unit)
        // Unchanged on the next sync.
        assertEquals(false, (engine().run() as SyncOutcome.Synced).profileChanged)
        assertTrue(requests.none { it.method == "PUT" })
    }

    @Test
    fun anAccountWithoutProfileGetsThePhonesBeforeUploading() = runBlocking {
        accountProfile = null
        phoneProfile = LocalProfile(30, "M", 25.0, "T2D", 0.02, 0.98)
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        assertTrue(engine().run() is SyncOutcome.Synced)
        val put = requests.single { it.method == "PUT" }
        assertEquals("/me/profile", put.url.encodedPath)
        val body = put.body!!.utf8()
        assertTrue(body, body.contains("\"sensitivity\":\"very_cautious\""))
        assertTrue(body, body.contains("\"diabetes_type\":\"T2D\""))
        assertTrue(requests.indexOf(put) < requests.indexOf(batchRequests().single()))
        assertEquals(0, queue.count())
    }

    @Test
    fun needsSetupWhenNeitherSideHasAProfile() = runBlocking {
        accountProfile = null
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        assertEquals(SyncOutcome.NeedsSetup, engine().run())
        assertEquals(1, queue.count())
        assertTrue(batchRequests().isEmpty())
    }

    private class FakeQueue : QueueDao {
        private val rows = sortedMapOf<Long, QueuedReading>()
        private val counter = MutableStateFlow(0)

        override suspend fun insert(reading: QueuedReading) {
            rows.putIfAbsent(reading.t, reading)
            counter.value = rows.size
        }

        override suspend fun insertAll(readings: List<QueuedReading>) = readings.forEach { insert(it) }

        override suspend fun oldest(limit: Int) = rows.values.take(limit)

        override suspend fun deleteByT(ts: List<Long>) {
            ts.forEach { rows.remove(it) }
            counter.value = rows.size
        }

        override suspend fun count() = rows.size

        override fun observeCount(): Flow<Int> = counter

        override suspend fun clear() {
            rows.clear()
            counter.value = 0
        }
    }
}
