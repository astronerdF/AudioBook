package com.example.kokoroandroid.logic

import android.util.Log

class SimplePhonemizer : Phonemizer {
    override fun phonemize(text: String): String {
        // TODO: This is a placeholder. Real Kokoro needs phonemes.
        // For now, we return the text. In a real app, we'd use eSpeak or a dictionary.
        Log.w("Kokoro", "Using SimplePhonemizer - output will be suboptimal")
        return text
    }
}
