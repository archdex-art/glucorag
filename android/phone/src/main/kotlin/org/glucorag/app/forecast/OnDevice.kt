package org.glucorag.app.forecast

import android.content.Context
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.glucorag.app.data.LocalDb
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.SessionStore
import org.glucorag.app.sync.AlertNotifier
import org.glucorag.app.sync.Pipeline
import org.glucorag.shared.GlucoseUnit
import java.time.ZoneId

/**
 * The forecast on this phone: after each kept reading (and when About you changes) it runs the
 * model on the stored readings, notifies new alerts, and publishes the snapshot that Today and
 * the watch show. Works the same with or without a server.
 */
object OnDevice {
    private const val MODEL_DIR = "model"

    @Volatile
    private var engine: ForecastEngine? = null
    private val running = Mutex()

    /** The bundled model, loaded once per process. */
    fun engine(context: Context): ForecastEngine = engine ?: synchronized(this) {
        engine ?: run {
            val assets = context.applicationContext.assets
            val meta = DeviceMeta.parse(assets.open("$MODEL_DIR/meta.json").bufferedReader().use { it.readText() })
            val bytes = assets.open("$MODEL_DIR/model.onnx").use { it.readBytes() }
            ForecastEngine(meta, OnnxModel(bytes, meta))
        }.also { engine = it }
    }

    /** One forecast cycle; cycles never overlap, so the alert memory stays consistent. */
    suspend fun run(context: Context, nowMs: Long = System.currentTimeMillis()) = running.withLock {
        val app = context.applicationContext
        val local = LocalState.get(app)
        val engine = engine(app)
        val readings = LocalDb.get(app).readings()
        // Enough before the newest kept reading for the model's history and the 3-hour chart.
        val newest = readings.newestT()
        val stored = if (newest == null) emptyList() else {
            readings.since(newest - maxOf(engine.meta.historySpanMin * MINUTE_MS, Forecaster.RECENT_MS)).map { it.toCgm() }
        }
        val unit = SessionStore(app).current().unit?.let(GlucoseUnit::parse) ?: GlucoseUnit.MG_DL
        val result = Forecaster(engine, ZoneId.systemDefault()).cycle(
            stored = stored,
            firstSeen = readings.oldestT(),
            latest = local.reading.value,
            profile = local.profile.value,
            unit = unit,
            memory = local.alertMemory,
            nowMs = nowMs,
        )
        local.alertMemory = result.memory
        val notifier = AlertNotifier(app)
        result.alerts.forEach { notifier.notify(it, unit, nowMs) }
        Pipeline.publishQuietly(app, local, result.snapshot)
    }

    private const val MINUTE_MS = 60_000L
}
