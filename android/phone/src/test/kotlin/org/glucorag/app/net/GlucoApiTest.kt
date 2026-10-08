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
    fun meParsesTheProfileAndIgnoresUnknownKeys() = runBlocking {
        token = "tok"
        json(
            """{"email":"a@b.c","role":"person","unit":"mmol/L",
               "profile":{"age":41,"gender":"F","bmi":23.4,"diabetes_type":"T1D","sensitivity":"cautious",
                          "hypo_quantile":0.1,"hyper_quantile":0.9},
               "readings":{"count":3,"first":null,"last":null},"model":{"version":"v7"}}""",
        )
        assertEquals(ProfileOut(41, "F", 23.4, "T1D", 0.1, 0.9), ok(api.me()).profile)
        val req = server.takeRequest()
        assertEquals("GET", req.method)
        assertEquals("/me", req.target)
        assertEquals("Bearer tok", req.headers["Authorization"])
    }

    @Test
    fun meWithoutProfile() = runBlocking {
        json("""{"email":"a@b.c","role":"person","unit":"mg/dL","profile":null}""")
        assertNull(ok(api.me()).profile)
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
        assertEquals(ApiResult.Unauthorized, api.me())
    }

    @Test
    fun conflictMapsToNeedsSetup() = runBlocking {
        json("""{"detail":"Set up your profile first."}""", 409)
        assertEquals(ApiResult.NeedsSetup, api.uploadBatch(listOf(CgmReading(0, 100.0, null, "xdrip"))))
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
