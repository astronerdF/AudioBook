package com.audiobook.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.audiobook.app.R
import com.audiobook.app.data.AudioBookApi
import com.audiobook.app.data.AudioBookRepository
import com.audiobook.app.data.Book
import com.audiobook.app.data.SampleContent
import com.audiobook.app.ui.theme.TextPrimary
import com.audiobook.app.ui.theme.TextSecondary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun LibraryScreen(modifier: Modifier = Modifier) {
    val books = remember { mutableStateListOf<Book>() }

    LaunchedEffect(Unit) {
        val fetched = withContext(Dispatchers.IO) {
            runCatching {
                val repo = AudioBookRepository(AudioBookApi.create(enableLogging = false))
                repo.fetchBooks()
            }.getOrNull()
        }
        books.clear()
        when {
            !fetched.isNullOrEmpty() -> books.addAll(fetched)
            else -> books.addAll(SampleContent.featured)
        }
    }

    if (books.isEmpty()) {
        EmptyLibraryState(modifier = modifier.fillMaxSize())
    } else {
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(horizontal = 20.dp, vertical = 64.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
            contentPadding = PaddingValues(bottom = 120.dp),
        ) {
            items(books, key = { it.id }) { book ->
                LibraryBookCard(book = book)
            }
        }
    }
}

@Composable
private fun EmptyLibraryState(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = stringResource(id = R.string.library_empty), color = TextSecondary, fontSize = 18.sp)
    }
}

@Composable
private fun LibraryBookCard(book: Book) {
    val shape = RoundedCornerShape(24.dp)
    Surface(
        modifier = Modifier
            .fillMaxSize()
            .clip(shape),
        color = Color.White.copy(alpha = 0.05f),
        tonalElevation = 0.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(alpha = 0.12f)),
    ) {
        Column(
            modifier = Modifier
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(text = book.title, color = TextPrimary, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
            Text(text = book.author, color = TextSecondary, fontSize = 14.sp)
            Text(
                text = book.chapters.take(3).joinToString(separator = " · ") { it.title },
                color = TextSecondary.copy(alpha = 0.8f),
                fontSize = 12.sp,
            )
        }
    }
}
