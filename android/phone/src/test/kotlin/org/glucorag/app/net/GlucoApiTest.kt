package org.glucorag.app.net

import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.glucorag.shared.CgmReading
import org.glucorag.shared.REASON_NEEDS_HTTPS
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import java.net.InetAddress
import java.time.OffsetDateTime
import java.util.concurrent.TimeUnit

class GlucoApiTest {
    private val server = MockWebServer()
    private var token: String? = null
    private lateinit var api: GlucoApi

    // checkServerUrl allows cleartext only to home/Tailscale addresses, so use the IPv4 loopback.
    private val base get() = "http://127.0.0.1:${server.port}"

    @Before
    fun setUp() {
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        api = GlucoApi(base, OkHttpClient(), { token })
    }

    @Test
    fun rejectedServerAddressCannotBuildApi() {
        val e = assertThrows(IllegalArgumentException::class.java) {
            GlucoApi("http://example.com", OkHttpClient(), { "tok" })
        }
        assertEquals(REASON_NEEDS_HTTPS, e.message)
        assertThrows(IllegalArgumentException::class.java) { GlucoApi("example.com", OkHttpClient(), { "tok" }) }
    }

    @After
    fun tearDown() = server.close()

    private fun json(body: String, code: Int = 200) = server.enqueue(
        MockResponse.Builder().code(code).setHeader("Content-Type", "application/json").body(body).build(),
    )

    private fun ms(iso: String) = OffsetDateTime.parse(iso).toInstant().toEpochMilli()

    private fun RecordedRequest.text() = body?.utf8() ?: ""

    private fun <T> ok(r: ApiResult<T>): T {
        assertTrue("expected Ok, got $r", r is ApiResult.Ok)
        return (r as ApiResult.Ok).value
    }

    @Test
    fun healthGetsHealthz() = runBlocking {
        json("""{"status":"ok","model_version":"v7"}""")
        assertEquals(Health("ok", "v7"), ok(api.health()))
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/healthz", req.target)
    }

    @Test
    fun signInPostsCredentialsWithoutBearer() = runBlocking {
        token = "stale"
        json(
            """{"token":"tok-1","expires_at":"2027-10-07T12:00:00.123456Z",
               "account":{"email":"a@b.c","role":"person","unit":"mmol/L","has_profile":true}}""",
        )
        val out = ok(api.signIn("a@b.c", "pw", "Pixel 9"))
        assertEquals("tok-1", out.token)
        assertEquals(ms("2027-10-07T12:00:00.123Z"), out.expiresAt)
        assertEquals(AccountOut("a@b.c", "person", "mmol/L", true), out.account)
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/auth/token", req.target)
        assertEquals("""{"email":"a@b.c","password":"pw","device":"Pixel 9"}""", req.text())
        assertTrue(req.headers["Content-Type"]!!.startsWith("application/json"))
        assertNull(req.headers["Authorization"])
    }

    @Test
    fun bearerHeaderPresentAfterSignIn() = runBlocking {
        json("""{"email":"a@b.c","role":"person","unit":"mg/dL","has_profile":false}""")
        api.account()
        assertNull(server.takeRequest().headers["Authorization"])

        json(
            """{"token":"tok-1","expires_at":"2027-10-07T12:00:00Z",
               "account":{"email":"a@b.c","role":"person","unit":"mg/dL","has_profile":false}}""",
        )
        token = ok(api.signIn("a@b.c", "pw", "Pixel")).token
        server.takeRequest()

        json("""{"email":"a@b.c","role":"person","unit":"mg/dL","has_profile":false}""")
        assertEquals(AccountOut("a@b.c", "person", "mg/dL", false), ok(api.account()))
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/auth/me", req.target)
        assertEquals("Bearer tok-1", req.headers["Authorization"])
    }

    @Test
    fun statusParsesRowPredictionAndIgnoresUnknownKeys() = runBlocking {
        token = "tok"
        json(
            """{"status":{"patient_id":"p1","diabetes_type":"T1D","status":"at_risk","severity":"high",
                 "last_reading":"2026-10-06T10:00:00+02:00","minutes_since_last":1.5,"stale":false,
                 "latest_t0":"2026-10-06T10:00:00+02:00","model_version":"v7",
                 "risk":[{"type":"hypo","horizon_min":30,"quantile":0.25,"value_mg_dl":65.0,
                          "extreme_mg_dl":60.0,"margin_mg_dl":-5.0,"severity":"high"}],
                 "active_alerts":["hypo"],"last_glucose_mg_dl":92.5,"trend_mg_dl_per_min":-1.2,
                 "forecast":{"t0":"2026-10-06T10:00:00+02:00","horizons":[15,30],"low_quantile":0.25,
                             "high_quantile":0.75,"low":[80.0,65.0],"median":[85.0,72.0],"high":[90.0,80.0]}},
               "prediction":{"patient_id":"p1","t0":"2026-10-06T10:00:00.250000+02:00","horizons":[15,30],
                             "quantiles":[0.25,0.5,0.75],"values":[[80.0,85.0,90.0],[65.0,72.0,80.0]],
                             "model_version":"v7"},
               "fresh":true,"hypo_quantile":0.25,"hyper_quantile":0.75,
               "now":"2026-10-06T10:01:30+02:00","model":{"version":"v7"}}""",
        )
        val s = ok(api.status())
        val t0 = ms("2026-10-06T08:00:00Z")
        assertEquals("at_risk", s.status.status)
        assertEquals(t0, s.status.lastReading)
        assertEquals(92.5, s.status.lastGlucoseMgDl!!, 0.0)
        assertEquals(-1.2, s.status.trendMgDlPerMin!!, 0.0)
        assertEquals(listOf(RiskFlagDto("hypo", 30, "high")), s.status.risk)
        assertEquals(
            ForecastBandDto(t0, listOf(15, 30), listOf(80.0, 65.0), listOf(85.0, 72.0), listOf(90.0, 80.0)),
            s.status.forecast,
        )
        val p = s.prediction!!
        assertEquals(t0 + 250, p.t0)
        assertEquals(listOf(0.25, 0.5, 0.75), p.quantiles)
        assertEquals(listOf(65.0, 72.0, 80.0), p.values[1])
        assertTrue(s.fresh)
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/me/status", req.target)
        assertEquals("Bearer tok", req.headers["Authorization"])
    }

    @Test
    fun statusWithoutReadingsOrPrediction() = runBlocking {
        json(
            """{"status":{"status":"no_data","last_reading":null,"risk":[],"forecast":null},
               "prediction":null,"fresh":false}""",
        )
        val s = ok(api.status())
        assertEquals("no_data", s.status.status)
        assertNull(s.status.lastReading)
        assertNull(s.status.lastGlucoseMgDl)
        assertNull(s.prediction)
    }

    @Test
    fun historyGetsReadings() = runBlocking {
        json(
            """{"readings":[{"timestamp":"2026-10-06T09:55:00+02:00","glucose_mg_dl":101.0,"flag":"ok"},
                            {"timestamp":"2026-10-06T10:00:00+02:00","glucose_mg_dl":99.5,"flag":"ok"}],
               "since":"2026-10-06T07:00:00+02:00","until":"2026-10-06T10:00:00+02:00"}""",
        )
        assertEquals(
            listOf(ReadingDto(ms("2026-10-06T07:55:00Z"), 101.0), ReadingDto(ms("2026-10-06T08:00:00Z"), 99.5)),
            ok(api.history()),
        )
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/me/history?hours=3", req.target)
    }

    @Test
    fun alertsAfterGetsNewerAlertsOldestFirst() = runBlocking {
        json(
            """[{"id":8,"patient_id":"p1","type":"hypo","horizon_min":30,"severity":"high",
                 "t_raised":"2026-10-06T10:00:00+02:00","t0":"2026-10-06T09:59:00+02:00",
                 "model_version":"v7","details":{"x":1}},
                {"id":9,"patient_id":"p1","type":"data_gap","horizon_min":null,"severity":null,
                 "t_raised":"2026-10-06T10:30:00+02:00","t0":null,"model_version":null,"details":{}}]""",
        )
        assertEquals(
            listOf(
                AlertDto(8, "hypo", "high", 30, ms("2026-10-06T08:00:00Z"), ms("2026-10-06T07:59:00Z")),
                AlertDto(9, "data_gap", null, null, ms("2026-10-06T08:30:00Z"), null),
            ),
            ok(api.alertsAfter(7)),
        )
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/me/alerts?after_id=7", req.target)
    }

    @Test
    fun uploadBatchSendsUtcIsoTimes() = runBlocking {
        json(
            """{"accepted":1,"already_present":1,
               "rejected":[{"timestamp":"2026-10-06T10:10:00+02:00","reason":"out_of_range"}]}""",
        )
        val t = ms("2026-10-06T08:00:00Z")
        val result = ok(
            api.uploadBatch(
                listOf(
                    CgmReading(t, 123.0, 1.5, "juggluco"),
                    CgmReading(t + 300_250, 98.4, null, "xdrip"),
                    CgmReading(t + 600_000, 700.0, null, "xdrip"),
                ),
            ),
        )
        assertEquals(BatchResult(1, 1, listOf(RejectedReading(t + 600_000, "out_of_range"))), result)
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/me/readings/batch", req.target)
        assertEquals(
            """{"readings":[{"timestamp":"2026-10-06T08:00:00Z","glucose_mg_dl":123.0},""" +
                """{"timestamp":"2026-10-06T08:05:00.250Z","glucose_mg_dl":98.4},""" +
                """{"timestamp":"2026-10-06T08:10:00Z","glucose_mg_dl":700.0}]}""",
            req.text(),
        )
    }

    @Test
    fun unauthorizedMapsTo401() = runBlocking {
        json("""{"detail":"Email or password is incorrect."}""", 401)
        assertEquals(ApiResult.Unauthorized, api.signIn("a@b.c", "bad", "Pixel"))
        json("""{"detail":"Not authenticated"}""", 401)
        assertEquals(ApiResult.Unauthorized, api.status())
    }

    @Test
    fun conflictMapsToNeedsSetup() = runBlocking {
        json("""{"detail":"Set up your profile first."}""", 409)
        assertEquals(ApiResult.NeedsSetup, api.status())
    }

    @Test
    fun tooLargeBatchMapsToHttpWithServerDetail() = runBlocking {
        json("""{"detail":"Batch larger than 500 readings"}""", 413)
        assertEquals(
            ApiResult.Http(413, "Batch larger than 500 readings"),
            api.uploadBatch(listOf(CgmReading(0, 100.0, null, "xdrip"))),
        )
    }

    @Test
    fun otherErrorsCarryDetailOrFallback() = runBlocking {
        json("""{"detail":"Device sign-in is for personal accounts."}""", 403)
        assertEquals(ApiResult.Http(403, "Device sign-in is for personal accounts."), api.signIn("d@r.c", "pw", "P"))
        server.enqueue(MockResponse.Builder().code(502).body("<html>bad gateway</html>").build())
        assertEquals(ApiResult.Http(502, "The server answered with error 502."), api.health())
        json("""{"detail":[{"loc":["body","email"],"msg":"bad"}]}""", 422)
        assertEquals(ApiResult.Http(422, "The server answered with error 422."), api.signIn("x", "pw", "P"))
    }

    @Test
    fun malformedSuccessBodyIsHttpError() = runBlocking {
        server.enqueue(MockResponse.Builder().code(200).body("<html>captive portal</html>").build())
        assertEquals(ApiResult.Http(200, "The server's answer wasn't understood."), api.health())
    }

    @Test
    fun timeoutMapsToNetwork() = runBlocking {
        val slow = GlucoApi(
            base,
            OkHttpClient.Builder().readTimeout(200, TimeUnit.MILLISECONDS).build(),
            { null },
        )
        server.enqueue(
            MockResponse.Builder().body("""{"status":"ok","model_version":"v7"}""")
                .headersDelay(2, TimeUnit.SECONDS).build(),
        )
        val r = slow.health()
        assertTrue("expected Network, got $r", r is ApiResult.Network)
    }

    @Test
    fun unreachableServerMapsToNetwork() = runBlocking {
        val closed = base
        server.close()
        val r = GlucoApi(closed, OkHttpClient(), { null }).health()
        assertTrue("expected Network, got $r", r is ApiResult.Network)
    }

    @Test
    fun defaultClientUsesAgreedTimeouts() {
        val c = GlucoApi.defaultClient()
        assertEquals(15_000, c.connectTimeoutMillis)
        assertEquals(30_000, c.readTimeoutMillis)
    }

    @Test
    fun signOutRevokesThisDeviceToken() = runBlocking {
        token = "tok-1"
        server.enqueue(MockResponse.Builder().code(204).build())
        val r = api.signOut()
        assertTrue("expected Ok, got $r", r is ApiResult.Ok<*>)
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/auth/logout", req.url.encodedPath)
        assertEquals("Bearer tok-1", req.headers["Authorization"])
    }

    @Test
    fun signOutWhenAlreadyRevokedIsUnauthorized() = runBlocking {
        token = "tok-1"
        json("""{"detail":"x"}""", 401)
        assertEquals(ApiResult.Unauthorized, api.signOut())
    }

    @Test
    fun pairPostsCodeWithoutBearerAndReturnsToken() = runBlocking {
        token = "old-account"
        json(
            """{"token":"tok-p","expires_at":"2027-10-07T12:00:00Z",
               "account":{"email":"noor@example.com","role":"person","unit":"mmol/L","has_profile":false}}""",
        )
        val out = ok(api.pair("ABCDEFGH", "Google Pixel 8"))
        assertEquals("tok-p", out.token)
        assertEquals(AccountOut("noor@example.com", "person", "mmol/L", false), out.account)
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/auth/pair", req.target)
        assertEquals("""{"code":"ABCDEFGH","device":"Google Pixel 8"}""", req.text())
        assertNull(req.headers["Authorization"])
    }

    @Test
    fun refusedPairingCodeCarriesTheServersExplanation() = runBlocking {
        json("""{"detail":"This pairing code is not valid. Make a new one on the website."}""", 401)
        assertEquals(
            ApiResult.Http(401, "This pairing code is not valid. Make a new one on the website."),
            api.pair("ABCDEFGH", "Pixel"),
        )
        json("""{"detail":"Too many attempts. Try again in a minute."}""", 429)
        assertEquals(ApiResult.Http(429, "Too many attempts. Try again in a minute."), api.pair("ABCDEFGH", "Pixel"))
    }

    @Test
    fun putProfileSendsAllFieldsWithBearer() = runBlocking {
        token = "tok-1"
        json("""{"email":"a@b.c","role":"person","unit":"mmol/L","profile":{"age":34},"readings":{"count":0}}""")
        val saved = ok(api.putProfile(ProfileIn(age = 34, gender = "F", bmi = 23.4, diabetesType = "T1D", sensitivity = "standard", unit = "mmol/L")))
        assertEquals(ProfileSaved("mmol/L"), saved)
        val req = server.takeRequest()
        assertEquals("PUT", req.method)
        assertEquals("/me/profile", req.target)
        assertEquals(
            """{"age":34,"gender":"F","bmi":23.4,"diabetes_type":"T1D","sensitivity":"standard","unit":"mmol/L"}""",
            req.text(),
        )
        assertEquals("Bearer tok-1", req.headers["Authorization"])
    }
}
