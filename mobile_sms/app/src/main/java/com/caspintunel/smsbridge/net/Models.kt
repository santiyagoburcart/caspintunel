package com.caspintunel.smsbridge.net

import com.google.gson.annotations.SerializedName

data class InboundRequest(
    val text: String,
    val sender: String?,
    @SerializedName("received_at") val receivedAt: String?,
)

/** Loosely typed — the endpoint always returns 201 with a small result dict;
 * we only care that the call succeeded, so we don't hard-fail on shape drift. */
data class InboundResponse(
    @SerializedName("message_id") val messageId: Long? = null,
    val matched: Boolean? = null,
    val reason: String? = null,
)

data class PingResponse(
    val device: String? = null,
    @SerializedName("server_time") val serverTime: String? = null,
)
