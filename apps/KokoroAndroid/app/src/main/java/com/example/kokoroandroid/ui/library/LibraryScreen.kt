package com.example.kokoroandroid.ui.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.example.kokoroandroid.model.Book
import java.io.File

@Composable
fun LibraryScreen(
    viewModel: LibraryViewModel = viewModel(),
    onBookClick: (Book) -> Unit
) {
    val books by viewModel.books.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(Color(0xFF121212), Color(0xFF000000))
                )
            )
    ) {
        if (isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.align(Alignment.Center),
                color = MaterialTheme.colorScheme.primary
            )
        } else {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "Good Evening",
                    style = MaterialTheme.typography.headlineMedium,
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 24.dp)
                )

                if (books.isEmpty()) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            text = "No books found.\nAdd .epub files to Documents or Downloads.",
                            color = Color.Gray,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                } else {
                    LazyVerticalGrid(
                        columns = GridCells.Adaptive(minSize = 100.dp),
                        horizontalArrangement = Arrangement.spacedBy(16.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        items(books) { book ->
                            BookItem(book = book, onClick = { onBookClick(book) })
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun BookItem(book: Book, onClick: () -> Unit) {
    Column(
        modifier = Modifier
            .width(100.dp)
            .clickable(onClick = onClick)
    ) {
        Card(
            shape = RoundedCornerShape(8.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
            modifier = Modifier
                .size(100.dp, 150.dp)
        ) {
            if (book.coverUri != null) {
                AsyncImage(
                    model = ImageRequest.Builder(LocalContext.current)
                        .data(File(book.coverUri))
                        .crossfade(true)
                        .build(),
                    contentDescription = "Cover for ${book.title}",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize()
                )
            } else {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color.DarkGray),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = book.title.take(1),
                        style = MaterialTheme.typography.headlineLarge,
                        color = Color.White
                    )
                }
            }
        }
        
        Spacer(modifier = Modifier.height(8.dp))
        
        Text(
            text = book.title,
            style = MaterialTheme.typography.bodyMedium,
            color = Color.White,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            fontWeight = FontWeight.SemiBold
        )
        
        Text(
            text = book.author,
            style = MaterialTheme.typography.labelSmall,
            color = Color.Gray,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}
