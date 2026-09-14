package com.caspintunel.smsbridge.data

import androidx.room.Entity
import androidx.room.PrimaryKey

enum class SendStatus { PENDING, SENT, FAILED }

@Entity(tableName = "sms_log")
data class SmsLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sender: String,
    val body: String,
    val receivedAtMillis: Long,
    var status: SendStatus = SendStatus.PENDING,
    var attempts: Int = 0,
    var lastError: String? = null,
    var updatedAtMillis: Long = receivedAtMillis,
)
