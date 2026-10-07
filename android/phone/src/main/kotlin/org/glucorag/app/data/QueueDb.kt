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
import kotlinx.coroutines.flow.Flow

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

@Database(entities = [QueuedReading::class], version = 1, exportSchema = false)
abstract class QueueDb : RoomDatabase() {
    abstract fun queue(): QueueDao

    companion object {
        @Volatile
        private var instance: QueueDb? = null

        fun get(context: Context): QueueDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext, QueueDb::class.java, "queue.db")
                .build()
                .also { instance = it }
        }
    }
}
