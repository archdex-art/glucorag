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
import org.glucorag.app.data.QueueDao
import org.glucorag.app.data.QueuedReading
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.AlertDto
import org.glucorag.app.net.GlucoApi
import org.glucorag.shared.CgmReading
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Snapshot
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.net.InetAddress
import java.time.Instant
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
    private val published = mutableListOf<Snapshot>()
    private val notified = mutableListOf<AlertDto>()

    // Server-side state the dispatcher serves.
    private var unit = "mg/dL"
    private var statusJson = status()
    private var alerts: List<String> = emptyList()
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
                    path == "/auth/me" -> json("""{"email":"a@example.com","role":"person","unit":"$unit","has_profile":true}""")
                    path == "/me/status" -> json(statusJson)
                    path == "/me/history" -> json(history())
                    path == "/me/alerts" -> {
                        val after = request.url.queryParameter("after_id")!!.toLong()
                        // Oldest first, capped at 2 per page to exercise paging.
                        val page = alerts.filter { idOf(it) > after }.take(2)
                        json(page.joinToString(",", "[", "]"))
                    }
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

    private fun iso(ms: Long) = Instant.ofEpochMilli(ms).toString()

    private fun idOf(alertJson: String) = Regex("\"id\":(\\d+)").find(alertJson)!!.groupValues[1].toLong()

    private fun alert(id: Long, type: String = "hypo", severity: String = "high", tRaised: Long = now) =
        """{"id":$id,"type":"$type","severity":"$severity","horizon_min":30,"t_raised":"${iso(tRaised)}"}"""

    private fun status(state: String = "ok", fresh: Boolean = true, lastReading: Long = now - 5 * min, risk: String = "[]") = """
        {"status":{"status":"$state","last_reading":"${iso(lastReading)}","last_glucose_mg_dl":150.0,
          "trend_mg_dl_per_min":1.5,"risk":$risk,
          "forecast":${if (fresh) """{"t0":"${iso(lastReading)}","horizons":[15,30,45,60],"low":[140,130,120,110],"median":[150,145,140,135],"high":[160,170,180,190]}""" else "null"}},
         "prediction":null,"fresh":$fresh}
    """.trimIndent()

    private fun history(): String {
        val points = (0..36).map { i -> """{"timestamp":"${iso(now - 5 * min - (36 - i) * 5 * min)}","glucose_mg_dl":${100 + i}.0}""" }
        return points.joinToString(",", """{"readings":[""", "]}")
    }

    private fun engine(latest: CgmReading? = null, last: Snapshot? = null, base: String = base()) = SyncEngine(
        api = GlucoApi(base, OkHttpClient(), { "tok" }),
        queue = queue,
        store = store,
        publish = { published += it },
        notify = { notified += it },
        clock = { now },
        latestReading = { latest },
        lastSnapshot = { last },
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
        assertTrue(outcome is SyncOutcome.Synced)
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
        val outcome = engine(latest = CgmReading(now - min, 120.0, 0.2, "juggluco")).run()
        assertTrue(outcome is SyncOutcome.SignedOut)
        assertEquals(1, queue.count())
        assertEquals("signed_out", published.last().server.state)
        assertEquals(120.0, published.last().now!!.mgdl, 0.0)
    }

    @Test
    fun networkFailurePublishesUnreachableWithoutForecast() = runBlocking {
        val closed = base()
        server.close()
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        val outcome = engine(latest = CgmReading(now - min, 120.0, 0.2, "juggluco"), base = closed).run()
        assertTrue(outcome is SyncOutcome.Retry)
        assertEquals(1, queue.count())
        val s = published.last()
        assertEquals("unreachable", s.server.state)
        assertNull(s.forecast)
        assertEquals(now - min, s.now!!.t)
    }

    @Test
    fun firstSyncAfterSignInDoesNotNotifyHistory() = runBlocking {
        alerts = listOf(alert(1), alert(2), alert(3), alert(4), alert(5))
        engine().run()
        assertTrue(notified.isEmpty())
        assertEquals(5L, store.current().lastAlertId)
    }

    @Test
    fun alertNotifiedOnceAcrossRestart() = runBlocking {
        store.update { it.copy(lastAlertId = 0L) }
        alerts = listOf(alert(1))
        engine().run()
        engine().run()
        assertEquals(listOf(1L), notified.map { it.id })
    }

    @Test
    fun replayedAlertWithNewIdNotNotifiedAgain() = runBlocking {
        store.update { it.copy(lastAlertId = 0L) }
        alerts = listOf(alert(1, tRaised = now - 5 * min))
        engine().run()
        // A backfill replays the same alert (same type and reading time) under a new id.
        alerts = listOf(alert(1, tRaised = now - 5 * min), alert(7, tRaised = now - 5 * min))
        engine().run()
        assertEquals(listOf(1L), notified.map { it.id })
        assertEquals(7L, store.current().lastAlertId)
    }

    @Test
    fun staleAlertNotNotified() = runBlocking {
        store.update { it.copy(lastAlertId = 0L) }
        alerts = listOf(alert(1, tRaised = now - 16 * min), alert(2, tRaised = now - 15 * min))
        engine().run()
        assertEquals(listOf(2L), notified.map { it.id })
    }

    @Test
    fun lowSeverityAndDataGapNotNotified() = runBlocking {
        store.update { it.copy(lastAlertId = 0L) }
        alerts = listOf(
            alert(1, severity = "low"),
            alert(2, type = "data_gap", severity = "medium"),
            alert(3, type = "hyper", severity = "medium"),
        )
        engine().run()
        assertEquals(listOf(3L), notified.map { it.id })
    }

    @Test
    fun snapshotUsesAccountUnitAndNewerLocalReading() = runBlocking {
        unit = "mmol/L"
        statusJson = status(risk = """[{"type":"hyper","horizon_min":45,"severity":"low"},{"type":"hypo","horizon_min":45,"severity":"medium"}]""")
        val local = CgmReading(now - min, 155.0, 2.5, "juggluco")
        engine(latest = local).run()
        val s = published.last()
        assertEquals(GlucoseUnit.MMOL_L, s.unit)
        assertEquals(local.t, s.now!!.t)
        assertEquals(155.0, s.now!!.mgdl, 0.0)
        assertEquals("ok", s.server.state)
        assertNotNull(s.forecast)
        assertEquals(now - 5 * min, s.forecast!!.t0)
        assertEquals(listOf(140.0, 130.0, 120.0, 110.0), s.forecast!!.low)
        // Same horizon: hypo before hyper (the website's sortFlags order).
        assertEquals("hypo", s.risk!!.type)
        assertEquals(now - 5 * min + 45 * min, s.risk!!.at)
        assertTrue(s.recent.size <= 37)
        assertEquals("mmol/L", store.current().unit)
    }

    @Test
    fun olderLocalReadingLosesToTheServer() = runBlocking {
        engine(latest = CgmReading(now - 30 * min, 90.0, null, "xdrip")).run()
        assertEquals(now - 5 * min, published.last().now!!.t)
        assertEquals(150.0, published.last().now!!.mgdl, 0.0)
    }

    @Test
    fun warmingUpAndStaleForecast() = runBlocking {
        statusJson = status(state = "warming_up", fresh = false)
        engine().run()
        assertEquals("warming_up", published.last().server.state)
        assertNull(published.last().forecast)
        assertNull(published.last().risk)
    }

    @Test
    fun needsSetupIsReported() = runBlocking {
        statusJson = "" // unused
        batchStatus = 409
        queue.insert(QueuedReading(now - min, 120.0, "juggluco"))
        val outcome = engine().run()
        assertTrue(outcome is SyncOutcome.NeedsSetup)
        assertEquals("needs_setup", published.last().server.state)
        assertEquals(1, queue.count())
    }

    @Test
    fun publishFailureDoesNotFailTheSync() = runBlocking {
        val failing = SyncEngine(
            api = GlucoApi(base(), OkHttpClient(), { "tok" }), queue = queue, store = store,
            publish = { error("no watch") }, notify = {}, clock = { now },
        )
        val outcome = failing.run()
        assertTrue(outcome is SyncOutcome.Synced)
        assertEquals(false, outcome.published)
    }

    private class FakeQueue : QueueDao {
        private val rows = sortedMapOf<Long, QueuedReading>()
        private val counter = MutableStateFlow(0)

        override suspend fun insert(reading: QueuedReading) {
            rows.putIfAbsent(reading.t, reading)
            counter.value = rows.size
        }

        override suspend fun oldest(limit: Int) = rows.values.take(limit)

        override suspend fun deleteByT(ts: List<Long>) {
            ts.forEach { rows.remove(it) }
            counter.value = rows.size
        }

        override suspend fun count() = rows.size

        override fun observeCount(): Flow<Int> = counter
    }
}
