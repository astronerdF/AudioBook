package com.audiobook.app.data

import androidx.compose.ui.graphics.Color
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Book(
    @SerialName("book_id") val id: String,
    val title: String,
    val author: String,
    val cover: String?,
    @SerialName("chapters") val chapters: List<ChapterSummary> = emptyList(),
)

@Serializable
data class ChapterSummary(
    val index: Int,
    val title: String,
    @SerialName("duration_ms") val durationMs: Long? = null,
    val audio: String? = null,
)

@Serializable
data class ChapterMetadata(
    @SerialName("chapter_index") val chapterIndex: Int,
    @SerialName("chapter_title") val chapterTitle: String,
    @SerialName("audio_file") val audioFile: String,
    @SerialName("duration_ms") val durationMs: Long,
    val text: String,
    val words: List<WordTiming>,
)

@Serializable
data class WordTiming(
    val token: String,
    @SerialName("start_ms") val startMs: Long,
    @SerialName("end_ms") val endMs: Long,
    @SerialName("char_start") val charStart: Int,
    @SerialName("char_end") val charEnd: Int,
)

object SampleContent {
    val featured = listOf(
        Book(
            id = "the-odyssey",
            title = "The Odyssey",
            author = "Homer",
            cover = null,
            chapters = listOf(
                ChapterSummary(index = 1, title = "Book I", durationMs = 15 * 60 * 1000L),
            ),
        ),
        Book(
            id = "moby-dick",
            title = "Moby-Dick",
            author = "Herman Melville",
            cover = null,
        ),
        Book(
            id = "sherlock",
            title = "Sherlock Holmes",
            author = "Arthur Conan Doyle",
            cover = null,
        ),
    )

    val continueListening = listOf(
        PlayingState(
            bookTitle = "Twenty Thousand Leagues",
            author = "Jules Verne",
            artworkColor = Color(0xFF364BFF),
            progress = 0.72f,
            durationLabel = "12m left",
        ),
        PlayingState(
            bookTitle = "Pride and Prejudice",
            author = "Jane Austen",
            artworkColor = Color(0xFFE2489F),
            progress = 0.38f,
            durationLabel = "25m left",
        ),
    )
}

data class PlayingState(
    val bookTitle: String,
    val author: String,
    val artworkColor: Color,
    val progress: Float,
    val durationLabel: String,
)
