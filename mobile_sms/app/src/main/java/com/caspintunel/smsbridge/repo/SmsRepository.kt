package com.caspintunel.smsbridge.repo

import android.content.Context
import android.util.Log
import androidx.lifecycle.LiveData
import com.caspintunel.smsbridge.data.AppDatabase
import com.caspintunel.smsbridge.data.Prefs
import com.caspintunel.smsbridge.data.SendStatus
import com.caspintunel.smsbridge.data.SmsLogEntity
import com.caspintunel.smsbridge.net.ApiClient
import com.caspintunel.smsbridge.net.InboundRequest
import com.caspintunel.smsbridge.net.PingResponse
import com.caspintunel.smsbridge.net.SmsSourceInfo
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

const val MAX_SEND_ATTEMPTS = 3
const val SOURCES_STALE_MILLIS = 30 * 60 * 1000L // refresh at least this often

private const val PING_PATH = "api/v1/payments/sms/ping/"
private const val INBOUND_PATH = "api/v1/payments/sms/inbound/"
private const val SOURCES_PATH = "api/v1/payments/sms/sources/"

class SmsRepository private constructor(context: Context) {
    private val dao = AppDatabase.get(context).smsLogDao()
    private val prefs = Prefs(context)
    private val api = ApiClient.service
    private val gson = Gson()
    private val sourcesListType = object : TypeToken<List<SmsSourceInfo>>() {}.type

    fun recentLog(limit: Int = 20): LiveData<List<SmsLogEntity>> = dao.recent(limit)

    suspend fun recordIncoming(sender: String, body: String, receivedAtMillis: Long): Long {
        val id = dao.insert(
            SmsLogEntity(sender = sender, body = body, receivedAtMillis = receivedAtMillis)
        )
        dao.trimTo(100)
        return id
    }

    suspend fun getEntry(id: Long): SmsLogEntity? = dao.get(id)

    /** One HTTP attempt for this log entry; updates its row with the outcome. */
    suspend fun attemptSend(entryId: Long): Boolean {
        val entry = dao.get(entryId) ?: return true // nothing to do — treat as done
        if (entry.status == SendStatus.SENT) return true
        if (!prefs.isConfigured()) {
            entry.status = SendStatus.FAILED
            entry.lastError = "server not configured"
            entry.updatedAtMillis = System.currentTimeMillis()
            dao.update(entry)
            return false
        }

        val url = ApiClient.buildUrl(prefs.normalizedServerUrl(), INBOUND_PATH)
        entry.attempts += 1
        return try {
            val resp = api.inbound(
                url,
                prefs.apiToken,
                InboundRequest(text = entry.body, sender = entry.sender, receivedAt = isoUtc(entry.receivedAtMillis)),
            )
            if (resp.isSuccessful) {
                entry.status = SendStatus.SENT
                entry.lastError = null
                entry.updatedAtMillis = System.currentTimeMillis()
                dao.update(entry)
                true
            } else {
                entry.status = SendStatus.FAILED
                entry.lastError = "HTTP ${resp.code()}: ${resp.errorBody()?.string()?.take(200)}"
                entry.updatedAtMillis = System.currentTimeMillis()
                dao.update(entry)
                false
            }
        } catch (e: Exception) {
            Log.w(TAG, "send failed for entry $entryId", e)
            entry.status = SendStatus.FAILED
            entry.lastError = e.message ?: e.javaClass.simpleName
            entry.updatedAtMillis = System.currentTimeMillis()
            dao.update(entry)
            false
        }
    }

    /** Manual "test connection" ping — also persists the result for the main screen.
     * A successful ping also refreshes the allowed-sender cache ("on reconnect"). */
    suspend fun ping(): Result<PingResponse> {
        if (!prefs.isConfigured()) return Result.failure(IllegalStateException("server not configured"))
        val url = ApiClient.buildUrl(prefs.normalizedServerUrl(), PING_PATH)
        return try {
            val resp = api.ping(url, prefs.apiToken)
            if (resp.isSuccessful && resp.body() != null) {
                val body = resp.body()!!
                prefs.lastPingOk = true
                prefs.lastPingMessage = "OK — ${body.device ?: "device"}"
                prefs.lastPingAtMillis = System.currentTimeMillis()
                refreshSources()
                Result.success(body)
            } else {
                val msg = "HTTP ${resp.code()}: ${resp.errorBody()?.string()?.take(200)}"
                prefs.lastPingOk = false
                prefs.lastPingMessage = msg
                prefs.lastPingAtMillis = System.currentTimeMillis()
                Result.failure(IllegalStateException(msg))
            }
        } catch (e: Exception) {
            prefs.lastPingOk = false
            prefs.lastPingMessage = e.message ?: e.javaClass.simpleName
            prefs.lastPingAtMillis = System.currentTimeMillis()
            Result.failure(e)
        }
    }

    /** Pulls the allowed-sender list from the server and replaces the local cache. */
    suspend fun refreshSources(): Result<List<SmsSourceInfo>> {
        if (!prefs.isConfigured()) return Result.failure(IllegalStateException("server not configured"))
        val url = ApiClient.buildUrl(prefs.normalizedServerUrl(), SOURCES_PATH)
        return try {
            val resp = api.sources(url, prefs.apiToken)
            val body = resp.body()
            if (resp.isSuccessful && body != null) {
                prefs.allowedSourcesJson = gson.toJson(body.sources)
                prefs.sourcesFetchedAtMillis = System.currentTimeMillis()
                Result.success(body.sources)
            } else {
                Result.failure(IllegalStateException("HTTP ${resp.code()}"))
            }
        } catch (e: Exception) {
            Log.w(TAG, "sources refresh failed", e)
            Result.failure(e)
        }
    }

    /** Cached allowed-sender list — never touches the network. */
    fun cachedSources(): List<SmsSourceInfo> {
        val json = prefs.allowedSourcesJson
        if (json.isBlank()) return emptyList()
        return try {
            gson.fromJson(json, sourcesListType) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun isSourcesCacheStale(): Boolean =
        System.currentTimeMillis() - prefs.sourcesFetchedAtMillis > SOURCES_STALE_MILLIS

    /** No sources configured yet -> nothing is filtered (matches the server's own
     * _resolve_source behavior: an empty allow-list means "allow everything"). */
    fun isSenderAllowed(sender: String?): Boolean {
        val allowed = cachedSources()
        if (allowed.isEmpty()) return true
        if (sender.isNullOrBlank()) return false
        val tail = normalizePhone(sender)
        if (tail.isEmpty()) return false
        return allowed.any { src ->
            val st = normalizePhone(src.phoneNumber)
            st.isNotEmpty() && (st == tail || st.endsWith(tail) || tail.endsWith(st))
        }
    }

    companion object {
        private const val TAG = "SmsRepository"

        @Volatile private var instance: SmsRepository? = null
        fun get(context: Context): SmsRepository =
            instance ?: synchronized(this) {
                instance ?: SmsRepository(context.applicationContext).also { instance = it }
            }

        private val isoFormat = ThreadLocal.withInitial {
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }
        }

        fun isoUtc(millis: Long): String = isoFormat.get()!!.format(Date(millis))

        private val PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

        /** Mirrors the backend's `_norm_phone`: strip to digits, take the last 10 —
         * a short code and a full MSISDN for the same sender still match this way. */
        fun normalizePhone(value: String): String {
            val digits = value.map { ch ->
                val i = PERSIAN_DIGITS.indexOf(ch)
                if (i >= 0) ('0' + i) else ch
            }.filter { it.isDigit() }.joinToString("")
            return if (digits.length >= 10) digits.takeLast(10) else digits
        }
    }
}
