package org.glucorag.app.forecast

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.glucorag.shared.CgmReading
import org.junit.AfterClass
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import java.io.File
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset

/**
 * The phone's engine against `parity.json`: raw readings run through the server's
 * `ForecastEngine.predict` (`glucorag-export-onnx --parity`). Readings there are naive local wall
 * times, so they are given here as UTC instants read in UTC.
 */
class ForecastEngineParityTest {
    private fun naive(iso: String): Long = LocalDateTime.parse(iso).toInstant(ZoneOffset.UTC).toEpochMilli()

    private fun readings(case: JsonObject) = case.getValue("readings").jsonArray.map {
        val (t, v) = it.jsonArray
        CgmReading(naive(t.jsonPrimitive.content), v.jsonPrimitive.double, null, "parity")
    }

    private fun features(case: JsonObject): Map<String, Any> = case.getValue("profile").jsonObject.mapValues { (_, v) ->
        val p = v.jsonPrimitive
        if (p.isString) p.content else p.double
    }

    private fun doubles(e: kotlinx.serialization.json.JsonElement) = e.jsonArray.map { it.jsonPrimitive.double }

    @Test
    fun fixturesCoverTheCasesTheServerHandles() {
        assertEquals(engine.meta.version, parity.getValue("model_version").jsonPrimitive.content)
        assertTrue(cases.size >= 10)
        assertTrue(cases.any { it.containsKey("error") })
    }

    @Test
    fun staticEncodingAndInputsMatchBuildInputs() {
        for (case in cases.filter { !it.containsKey("error") }) {
            val name = case.getValue("name").jsonPrimitive.content
            val static = engine.encodeStatic(features(case))
            doubles(case.getValue("static")).forEachIndexed { i, v -> assertEquals(name, v, static[i].toDouble(), 1e-6) }
            val inputs = engine.buildInputs(readings(case), ZoneOffset.UTC)
            assertEquals(name, naive(case.getValue("t0").jsonPrimitive.content), inputs.t0)
            case.getValue("x_enc").jsonArray.forEachIndexed { i, row ->
                doubles(row).forEachIndexed { j, v -> assertEquals("$name x_enc[$i][$j]", v, inputs.xEnc[i][j].toDouble(), 1e-6) }
            }
            case.getValue("x_dec").jsonArray.forEachIndexed { i, row ->
                assertEquals("$name x_dec[$i]", doubles(row).single(), inputs.xDec[i].toDouble(), 1e-6)
            }
        }
    }

    @Test
    fun forecastMatchesThePythonEngineWithinHalfAMilligram() {
        var checked = 0
        for (case in cases) {
            val name = case.getValue("name").jsonPrimitive.content
            if (case.containsKey("error")) {
                assertThrows(name, DataGapException::class.java) { engine.predict(features(case), readings(case), ZoneOffset.UTC) }
                continue
            }
            val f = engine.predict(features(case), readings(case), ZoneOffset.UTC)
            val want = case.getValue("values").jsonArray
            assertEquals(name, want.size, f.values.size)
            want.forEachIndexed { h, row ->
                doubles(row).forEachIndexed { q, v -> assertEquals("$name [$h][$q]", v, f.values[h][q], 0.5) }
            }
            checked++
        }
        assertTrue(checked >= 8)
    }

    /** The server reads times as local wall-clock time: the phone does the same in its own zone. */
    @Test
    fun timesAreReadAsLocalWallClockTime() {
        val case = cases.first { !it.containsKey("error") }
        val zone = ZoneId.of("America/New_York")
        // The same wall-clock readings, taken in New York.
        val local = readings(case).map {
            val wall = LocalDateTime.ofEpochSecond(it.t / 1000, 0, ZoneOffset.UTC)
            it.copy(t = wall.atZone(zone).toInstant().toEpochMilli())
        }
        val inZone = engine.buildInputs(local, zone)
        val naive = engine.buildInputs(readings(case), ZoneOffset.UTC)
        assertEquals(naive.xDec.toList(), inZone.xDec.toList())
        assertEquals(naive.xEnc.map { it.toList() }, inZone.xEnc.map { it.toList() })
    }

    companion object {
        private lateinit var model: OnnxModel
        private lateinit var engine: ForecastEngine
        private lateinit var parity: JsonObject
        private lateinit var cases: List<JsonObject>

        @BeforeClass
        @JvmStatic
        fun load() {
            // Unit tests run in the module directory.
            val assets = File("src/main/assets/model")
            val meta = DeviceMeta.parse(assets.resolve("meta.json").readText())
            model = OnnxModel(assets.resolve("model.onnx").readBytes(), meta)
            engine = ForecastEngine(meta, model)
            val text = ForecastEngineParityTest::class.java.getResource("/parity.json")!!.readText()
            parity = Json.parseToJsonElement(text).jsonObject
            cases = (parity.getValue("cases") as JsonArray).map { it.jsonObject }
        }

        @AfterClass
        @JvmStatic
        fun close() = model.close()
    }
}
