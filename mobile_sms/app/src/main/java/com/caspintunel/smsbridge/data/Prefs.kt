package com.caspintunel.smsbridge.data

import android.content.Context
import android.content.SharedPreferences

/** Server URL + device token, and the last ping result shown on the main screen. */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.applicationContext.getSharedPreferences("sms_bridge_prefs", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = sp.getString(KEY_SERVER_URL, "") ?: ""
        set(value) = sp.edit().putString(KEY_SERVER_URL, value.trim()).apply()

    var apiToken: String
        get() = sp.getString(KEY_API_TOKEN, "") ?: ""
        set(value) = sp.edit().putString(KEY_API_TOKEN, value.trim()).apply()

    var lastPingOk: Boolean?
        get() = if (sp.contains(KEY_LAST_PING_OK)) sp.getBoolean(KEY_LAST_PING_OK, false) else null
        set(value) {
            if (value == null) sp.edit().remove(KEY_LAST_PING_OK).apply()
            else sp.edit().putBoolean(KEY_LAST_PING_OK, value).apply()
        }

    var lastPingMessage: String
        get() = sp.getString(KEY_LAST_PING_MSG, "") ?: ""
        set(value) = sp.edit().putString(KEY_LAST_PING_MSG, value).apply()

    var lastPingAtMillis: Long
        get() = sp.getLong(KEY_LAST_PING_AT, 0L)
        set(value) = sp.edit().putLong(KEY_LAST_PING_AT, value).apply()

    // cached allowed-sender list, as raw JSON (see SmsRepository for (de)serialization) —
    // kept here rather than Room since it's a small, whole-list replace-on-refresh cache
    var allowedSourcesJson: String
        get() = sp.getString(KEY_SOURCES_JSON, "") ?: ""
        set(value) = sp.edit().putString(KEY_SOURCES_JSON, value).apply()

    var sourcesFetchedAtMillis: Long
        get() = sp.getLong(KEY_SOURCES_AT, 0L)
        set(value) = sp.edit().putLong(KEY_SOURCES_AT, value).apply()

    fun isConfigured(): Boolean = serverUrl.isNotBlank() && apiToken.isNotBlank()

    /** Normalized so callers can safely do "$base/api/v1/...". */
    fun normalizedServerUrl(): String = serverUrl.trimEnd('/')

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_API_TOKEN = "api_token"
        private const val KEY_LAST_PING_OK = "last_ping_ok"
        private const val KEY_LAST_PING_MSG = "last_ping_msg"
        private const val KEY_LAST_PING_AT = "last_ping_at"
        private const val KEY_SOURCES_JSON = "allowed_sources_json"
        private const val KEY_SOURCES_AT = "sources_fetched_at"
    }
}
