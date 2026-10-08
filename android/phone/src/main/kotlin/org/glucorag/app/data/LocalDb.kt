package org.glucorag.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import kotlinx.coroutines.flow.Flow
import org.glucorag.shared.CgmReading

/** A reading waiting for upload: [t] epoch ms (one row per time), [mgdl], [from] the source app. */
@Entity(tableName = "queue")
data class QueuedReading(
    @PrimaryKey val t: Long,
    val mgdl: Double,
    val from: String,
)

/** The upload queue, oldest first. */
@Dao
interface QueueDao {
    /** A reading already queued at the same time is kept. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(reading: QueuedReading)

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertAll(readings: List<QueuedReading>)

    @Query("SELECT * FROM queue ORDER BY t ASC LIMIT :limit")
    suspend fun oldest(limit: Int): List<QueuedReading>

    /** [ts] stays far below SQLite's bound-variable limit: batches are ≤ 500. */
    @Query("DELETE FROM queue WHERE t IN (:ts)")
    suspend fun deleteByT(ts: List<Long>)

    @Query("SELECT COUNT(*) FROM queue")
    suspend fun count(): Int

    /** The number of waiting readings, for the sync line. */
    @Query("SELECT COUNT(*) FROM queue")
    fun observeCount(): Flow<Int>

    /** Drops every waiting reading (a confirmed sign-out). */
    @Query("DELETE FROM queue")
    suspend fun clear()
}

/**
 * A reading kept on the phone (≈ one per 5 min, [KEEP_MS] back): the forecast's history, the
 * chart, and what uploads when the phone connects to a server later.
 */
@Entity(tableName = "readings")
data class StoredReading(
    @PrimaryKey val t: Long,
    val mgdl: Double,
    val from: String,
) {
    fun toCgm() = CgmReading(t, mgdl, null, from)

    companion object {
        /** A week: enough for the chart, the forecast, and a late first upload. */
        const val KEEP_MS = 7 * 24 * 60 * 60_000L
    }
}

/** The phone's own readings, oldest first. */
@Dao
interface ReadingDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(readings: List<StoredReading>)

    @Query("SELECT * FROM readings WHERE t >= :t ORDER BY t ASC")
    suspend fun since(t: Long): List<StoredReading>

    @Query("SELECT MIN(t) FROM readings")
    suspend fun oldestT(): Long?

    @Query("SELECT MAX(t) FROM readings")
    suspend fun newestT(): Long?

    /** Every kept reading, for the first upload after connecting to a server. */
    @Query("SELECT * FROM readings ORDER BY t ASC")
    suspend fun all(): List<StoredReading>

    @Query("DELETE FROM readings WHERE t < :t")
    suspend fun deleteBefore(t: Long)

    @Query("DELETE FROM readings")
    suspend fun clear()
}

@Database(entities = [QueuedReading::class, StoredReading::class], version = 2, exportSchema = false)
abstract class LocalDb : RoomDatabase() {
    abstract fun queue(): QueueDao

    abstract fun readings(): ReadingDao

    companion object {
        /** 0.2 → 0.3: the phone keeps its own readings (it forecasts on the device). */
        private val V1_TO_V2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("CREATE TABLE IF NOT EXISTS `readings` (`t` INTEGER NOT NULL, `mgdl` REAL NOT NULL, `from` TEXT NOT NULL, PRIMARY KEY(`t`))")
            }
        }

        @Volatile
        private var instance: LocalDb? = null

        // The file keeps its 0.2 name, so an update keeps the upload queue.
        fun get(context: Context): LocalDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext, LocalDb::class.java, "queue.db")
                .addMigrations(V1_TO_V2)
                .build()
                .also { instance = it }
        }
    }
}
