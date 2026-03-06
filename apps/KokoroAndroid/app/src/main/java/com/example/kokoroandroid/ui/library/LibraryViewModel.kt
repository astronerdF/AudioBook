package com.example.kokoroandroid.ui.library

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.kokoroandroid.data.BookRepository
import com.example.kokoroandroid.model.Book
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class LibraryViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = BookRepository(application)

    private val _books = MutableStateFlow<List<Book>>(emptyList())
    val books: StateFlow<List<Book>> = _books.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    init {
        loadBooks()
    }

    fun loadBooks() {
        viewModelScope.launch {
            _isLoading.value = true
            _books.value = repository.scanBooks()
            _isLoading.value = false
        }
    }
}
