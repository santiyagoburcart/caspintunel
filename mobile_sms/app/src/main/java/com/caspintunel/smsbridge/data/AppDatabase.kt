package com.caspintunel.smsbridge.data

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverter
import androidx.room.TypeConverters

class Converters {
    @TypeConverter
    fun fromStatus(status: SendStatus): String = status.name

    @TypeConverter
    fun toStatus(value: String): SendStatus = SendStatus.valueOf(value)
}

@Database(entities = [SmsLogEntity::class], version = 1, exportSchema = false)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun smsLogDao(): SmsLogDao

    companion object {
        @Volatile private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "sms_bridge.db",
                ).fallbackToDestructiveMigration().build().also { instance = it }
            }
    }
}
