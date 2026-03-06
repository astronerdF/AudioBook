package com.example.kokoroandroid.model

data class Book(
    val id: String,
    val title: String,
    val author: String,
    val coverUri: String?, // Path to cached cover image
    val filePath: String,  // Path to original EPUB file
    val progress: Float = 0f // 0.0 to 1.0
)
