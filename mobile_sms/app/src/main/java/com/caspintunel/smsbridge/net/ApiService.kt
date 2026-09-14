package com.caspintunel.smsbridge.net

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Url

interface ApiService {
    // full URLs are passed in explicitly (server + token are user-configurable
    // at runtime, so we can't bake a fixed @Retrofit baseUrl into the interface)

    @GET
    suspend fun ping(
        @Url url: String,
        @Header("X-Device-Token") token: String,
    ): Response<PingResponse>

    @POST
    suspend fun inbound(
        @Url url: String,
        @Header("X-Device-Token") token: String,
        @Body body: InboundRequest,
    ): Response<InboundResponse>

    @GET
    suspend fun sources(
        @Url url: String,
        @Header("X-Device-Token") token: String,
    ): Response<SourcesResponse>
}
