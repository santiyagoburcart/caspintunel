package com.caspintunel.smsbridge.data

import androidx.lifecycle.LiveData
import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface SmsLogDao {
    @Insert
    suspend fun insert(entry: SmsLogEntity): Long

    @Update
    suspend fun update(entry: SmsLogEntity)

    @Query("SELECT * FROM sms_log WHERE id = :id")
    suspend fun get(id: Long): SmsLogEntity?

    @Query("SELECT * FROM sms_log ORDER BY receivedAtMillis DESC LIMIT :limit")
    fun recent(limit: Int = 20): LiveData<List<SmsLogEntity>>

    // keep only the last 100 rows so the local log never grows without bound
    @Query(
        "DELETE FROM sms_log WHERE id NOT IN " +
            "(SELECT id FROM sms_log ORDER BY receivedAtMillis DESC LIMIT :keep)"
    )
    suspend fun trimTo(keep: Int = 100)
}
