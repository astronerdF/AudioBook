package com.audiobook.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class AudioBookRepository(
    private val service: AudioBookService,
) {
    suspend fun fetchBooks(): List<Book> = withContext(Dispatchers.IO) {
        service.listBooks()
    }

    suspend fun fetchChapterMetadata(bookId: String, chapterIndex: Int): ChapterMetadata = withContext(Dispatchers.IO) {
        service.getChapterMetadata(bookId, chapterIndex)
    }
}
