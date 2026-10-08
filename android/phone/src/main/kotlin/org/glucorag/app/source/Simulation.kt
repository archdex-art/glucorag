package org.glucorag.app.source

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import org.glucorag.app.data.LocalState
import org.glucorag.app.data.SessionStore
import org.glucorag.app.sync.Pipeline
import java.util.concurrent.TimeUnit

/**
 * Simulated readings ([SimulatedFeed]) through the same path as Juggluco's and xDrip+'s
 * broadcasts: [Pipeline.receiveAll] keeps them, forecasts, and queues them when a server is set. On start the last 3 h arrive at
 * once; then [SimulatedWorker] adds the readings due every 5 minutes until [stop] or sign-out.
 */
object Simulation {
    private const val WORK = "simulated_readings"

    /** Turns simulated readings on and feeds the last 3 h. Finishes even if the screen goes away. */
    suspend fun start(context: Context) = withContext(NonCancellable) {
        val app = context.applicationContext
        SessionStore(app).update { it.copy(simulated = true) }
        schedule(app, ExistingWorkPolicy.REPLACE)
        feed(app)
    }

    suspend fun stop(context: Context) = withContext(NonCancellable) {
        val app = context.applicationContext
        cancel(app)
        SessionStore(app).update { it.copy(simulated = false) }
    }

    /** Stops the timer only; signing in also resets the stored on/off. */
    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(WORK)
    }

    /** Feeds every reading due since the phone's newest one, at most the last 3 h. */
    internal suspend fun feed(context: Context, nowMs: Long = System.currentTimeMillis()) {
        val after = LocalState.get(context).reading.value?.t
        Pipeline.receiveAll(context, SimulatedFeed.readings(after, nowMs), nowMs)
    }

    /**
     * The next run in 5 minutes. From inside a running worker use APPEND_OR_REPLACE: the next run
     * waits for this one to finish instead of cancelling it.
     */
    internal fun schedule(context: Context, policy: ExistingWorkPolicy) {
        val request = OneTimeWorkRequestBuilder<SimulatedWorker>()
            .setInitialDelay(SimulatedFeed.STEP_MS, TimeUnit.MILLISECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(WORK, policy, request)
    }
}

/** One simulated tick: feeds the readings due (including any missed while asleep) and re-arms. */
class SimulatedWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext
        if (!SessionStore(app).current().simulated) return Result.success()
        Simulation.feed(app)
        Simulation.schedule(app, ExistingWorkPolicy.APPEND_OR_REPLACE)
        return Result.success()
    }
}
