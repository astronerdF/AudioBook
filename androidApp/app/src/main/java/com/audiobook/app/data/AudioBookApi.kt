package com.audiobook.app.data

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.GET
import retrofit2.http.Path

interface AudioBookService {
    @GET("books")
    suspend fun listBooks(): List<Book>

    @GET("books/{bookId}/chapters/{chapterIndex}/metadata")
    suspend fun getChapterMetadata(
        @Path("bookId") bookId: String,
        @Path("chapterIndex") chapterIndex: Int,
    ): ChapterMetadata
}

object AudioBookApi {
    private const val DEFAULT_BASE_URL = "http://10.0.2.2:8000/api/"

    private val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
    }

    fun create(
        baseUrl: String = DEFAULT_BASE_URL,
        enableLogging: Boolean = true,
    ): AudioBookService {
        val logger = HttpLoggingInterceptor().apply {
            level = if (enableLogging) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(logger)
            .build()

        val contentType = "application/json".toMediaType()

        val retrofit = Retrofit.Builder()
            .baseUrl(baseUrl)
            .addConverterFactory(json.asConverterFactory(contentType))
            .client(client)
            .build()

        return retrofit.create(AudioBookService::class.java)
    }
}
