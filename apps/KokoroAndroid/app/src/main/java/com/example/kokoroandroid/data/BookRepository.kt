package com.example.kokoroandroid.data

import android.content.Context
import android.os.Environment
import android.util.Log
import com.example.kokoroandroid.model.Book
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

class BookRepository(private val context: Context) {
    private val epubParser = EpubParser(context)

    suspend fun scanBooks(): List<Book> = withContext(Dispatchers.IO) {
        val books = mutableListOf<Book>()
        
        // Scan standard directories
        val dirsToScan = listOf(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS)
        )

        for (dir in dirsToScan) {
            if (dir.exists() && dir.isDirectory) {
                scanDirectory(dir, books)
            }
        }
        
        // Sort by title
        books.sortedBy { it.title }
    }

    private fun scanDirectory(dir: File, books: MutableList<Book>) {
        try {
            val files = dir.listFiles() ?: return
            for (file in files) {
                if (file.isDirectory) {
                    scanDirectory(file, books)
                } else if (file.extension.equals("epub", ignoreCase = true)) {
                    val book = epubParser.parseEpub(file)
                    if (book != null) {
                        books.add(book)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("BookRepository", "Error scanning directory ${dir.path}", e)
        }
    }
}
