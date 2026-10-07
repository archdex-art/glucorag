package org.glucorag.app.sync

import org.glucorag.app.data.QueueDao
import org.glucorag.app.data.SessionStore
import org.glucorag.app.net.AlertDto
import org.glucorag.app.net.ApiResult
import org.glucorag.app.net.GlucoApi
import org.glucorag.app.net.ReadingDto
import org.glucorag.app.net.StatusDto
import org.glucorag.shared.CgmReading
import org.glucorag.shared.Forecast
import org.glucorag.shared.GlucoseUnit
import org.glucorag.shared.Now
import org.glucorag.shared.Risk
import org.glucorag.shared.Server
import org.glucorag.shared.Snapshot
import org.glucorag.shared.SnapshotCodec
import kotlin.coroutines.cancellation.CancellationException

/** What one sync achieved, with the snapshot it published for the watch and the phone UI. */
sealed interface SyncOutcome {
    val snapshot: Snapshot
    val published: Boolean

    /** [uploaded] readings left the queue; [refused] of them the server rejected (time, range). */
    data class Synced(
        override val snapshot: Snapshot,
        override val published: Boolean,
        val uploaded: Int,
        val refused: Int,
    ) : SyncOutcome

    /** The token was revoked or expired: uploads stop, the queue is kept for the next sign-in. */
    data class SignedOut(override val snapshot: Snapshot, override val published: Boolean) : SyncOutcome

    /** The account has no profile yet (website setup unfinished). */
    data class NeedsSetup(override val snapshot: Snapshot, override val published: Boolean) : SyncOutcome

    /** The server could not be reached or failed; try again later. */
    data class Retry(override val snapshot: Snapshot, override val published: Boolean, val reason: String) : SyncOutcome
}

/**
 * One sync: drain the upload queue, fetch status/history/new alerts, notify, and publish a
 * [Snapshot]. Pure Kotlin over [GlucoApi], [QueueDao] and [SessionStore], so it runs on the JVM in
 * tests. [latestReading] is the newest CGM reading this phone received (it may be newer than the
 * server's); [lastSnapshot] is the previous snapshot, reused when the server can't be asked.
 */
class SyncEngine(
    private val api: GlucoApi,
    private val queue: QueueDao,
    private val store: SessionStore,
    private val publish: suspend (Snapshot) -> Unit,
    private val notify: (AlertDto) -> Unit,
    private val clock: () -> Long,
    private val latestReading: () -> CgmReading? = { null },
    private val lastSnapshot: () -> Snapshot? = { null },
) {
    /** A failed API call, carried out of the happy path. */
    private class Stop(val result: ApiResult<Nothing>) : Exception(null, null, false, false)

    suspend fun run(): SyncOutcome {
        var uploaded = 0
        var refused = 0
        return try {
            // Re-read the queue after every batch: readings queued during the upload are sent too.
            while (true) {
                val batch = queue.oldest(BATCH_SIZE)
                if (batch.isEmpty()) break
                val result = ok(api.uploadBatch(batch.map { CgmReading(it.t, it.mgdl, null, it.from) }))
                queue.deleteByT(batch.map { it.t })
                uploaded += batch.size
                refused += result.rejected.size
            }
            val account = ok(api.account())
            val unit = GlucoseUnit.parse(account.unit)
            store.update { it.copy(unit = account.unit) }
            val status = ok(api.status())
            val history = ok(api.history(HISTORY_HOURS))
            handleAlerts()
            val snapshot = online(unit, status, history)
            SyncOutcome.Synced(snapshot, tryPublish(snapshot), uploaded, refused)
        } catch (stop: Stop) {
            when (val r = stop.result) {
                ApiResult.Unauthorized -> offline("signed_out").let { SyncOutcome.SignedOut(it, tryPublish(it)) }
                ApiResult.NeedsSetup -> offline("needs_setup").let { SyncOutcome.NeedsSetup(it, tryPublish(it)) }
                is ApiResult.Network -> offline("unreachable").let { SyncOutcome.Retry(it, tryPublish(it), r.cause.message ?: "network") }
                is ApiResult.Http -> offline("unreachable").let { SyncOutcome.Retry(it, tryPublish(it), "HTTP ${r.code}: ${r.message}") }
                is ApiResult.Ok -> error("unreachable")
            }
        }
    }

    private fun <T> ok(result: ApiResult<T>): T = when (result) {
        is ApiResult.Ok -> result.value
        ApiResult.Unauthorized -> throw Stop(ApiResult.Unauthorized)
        ApiResult.NeedsSetup -> throw Stop(ApiResult.NeedsSetup)
        is ApiResult.Http -> throw Stop(result)
        is ApiResult.Network -> throw Stop(result)
    }

    /**
     * Pages through alerts newer than the last handled id. The first sync after sign-in only
     * records the newest id, so history never buzzes. Afterwards an alert buzzes when it is a
     * high/medium low or high, was raised from a reading at most [ALERT_FRESH_MS] old, and its
     * (type, reading time) was not notified before: the server re-raises replayed alerts under
     * new ids when older readings arrive.
     */
    private suspend fun handleAlerts() {
        val session = store.current()
        val baseline = session.lastAlertId == null
        var after = session.lastAlertId ?: 0L
        val notified = session.notifiedAlerts.toMutableList()
        val now = clock()
        while (true) {
            val page = ok(api.alertsAfter(after))
            if (page.isEmpty()) break
            for (alert in page) {
                after = maxOf(after, alert.id)
                if (baseline || !buzzes(alert, now)) continue
                val key = "${alert.type}@${alert.tRaised}"
                if (key in notified) continue
                notify(alert)
                notified += key
            }
        }
        store.update { it.copy(lastAlertId = after, notifiedAlerts = notified.takeLast(NOTIFIED_KEPT)) }
    }

    private fun buzzes(a: AlertDto, now: Long) =
        a.type in setOf("hypo", "hyper") && a.severity in setOf("high", "medium") && now - a.tRaised <= ALERT_FRESH_MS

    private fun online(unit: GlucoseUnit, status: StatusDto, history: List<ReadingDto>): Snapshot {
        val row = status.status
        val serverNow = row.lastReading?.let { t -> row.lastGlucoseMgDl?.let { Now(t, it, row.trendMgDlPerMin, "server") } }
        val band = row.forecast.takeIf { status.fresh }
        val forecast = band?.let { Forecast(it.t0, it.horizons, it.median, it.low, it.high) }
        // The website's sortFlags order: earliest horizon first, hypo before hyper.
        val first = row.risk.sortedWith(compareBy({ it.horizonMin }, { if (it.type == "hypo") 0 else 1 })).firstOrNull()
        val risk = if (band != null && first != null) Risk(first.type, band.t0 + first.horizonMin * MINUTE_MS, first.severity) else null
        val state = if (row.status == "warming_up") "warming_up" else "ok"
        val now = clock()
        return Snapshot(
            v = SnapshotCodec.VERSION,
            unit = unit,
            now = newer(localNow(), serverNow),
            recent = recent(history),
            forecast = forecast,
            risk = risk,
            server = Server(state, now),
            written = now,
        )
    }

    /** Without the server: the last known picture, the newest local reading, and no forecast. */
    private suspend fun offline(state: String): Snapshot {
        val last = lastSnapshot()
        val unit = store.current().unit?.let(GlucoseUnit::parse) ?: last?.unit ?: GlucoseUnit.MG_DL
        val now = clock()
        return Snapshot(
            v = SnapshotCodec.VERSION,
            unit = unit,
            now = newer(localNow(), last?.now),
            recent = last?.recent ?: emptyList(),
            forecast = null,
            risk = null,
            server = Server(state, now),
            written = now,
        )
    }

    private fun localNow() = latestReading()?.let { Now(it.t, it.mgdl, it.ratePerMin, it.from) }

    private fun newer(a: Now?, b: Now?) = listOfNotNull(a, b).maxByOrNull { it.t }

    /** History thinned to ≥ 4.5 min spacing, the last [RECENT_POINTS] points. */
    private fun recent(history: List<ReadingDto>): List<List<Double>> {
        val kept = mutableListOf<ReadingDto>()
        for (r in history.sortedBy { it.t }) {
            if (kept.isEmpty() || r.t - kept.last().t >= THIN_MS) kept += r
        }
        return kept.takeLast(RECENT_POINTS).map { listOf(it.t.toDouble(), it.mgdl) }
    }

    private suspend fun tryPublish(s: Snapshot): Boolean = try {
        publish(s)
        true
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        false
    }

    companion object {
        const val BATCH_SIZE = 500
        const val HISTORY_HOURS = 3
        const val RECENT_POINTS = 37
        const val THIN_MS = 270_000L
        const val ALERT_FRESH_MS = 15 * 60_000L
        const val NOTIFIED_KEPT = 50
        private const val MINUTE_MS = 60_000L
    }
}
