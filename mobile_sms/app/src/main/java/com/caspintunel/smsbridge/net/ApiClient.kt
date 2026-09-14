package com.caspintunel.smsbridge.net

import com.caspintunel.smsbridge.BuildConfig
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    // @Url on every call is an absolute URL built from the user's server setting,
    // so this base is never actually dereferenced — Retrofit just requires one.
    private const val DUMMY_BASE = "http://localhost/"

    val service: ApiService by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE
        }
        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .addInterceptor(logging)
            .build()

        Retrofit.Builder()
            .baseUrl(DUMMY_BASE)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    /** e.g. base="https://panel.example.com", path="api/v1/payments/sms/ping/" */
    fun buildUrl(base: String, path: String): String =
        "${base.trimEnd('/')}/${path.trimStart('/')}"
}
