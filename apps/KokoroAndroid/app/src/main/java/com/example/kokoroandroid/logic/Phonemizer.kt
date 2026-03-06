package com.example.kokoroandroid.logic

interface Phonemizer {
    fun phonemize(text: String): String
}

class DummyPhonemizer : Phonemizer {
    override fun phonemize(text: String): String {
        // TODO: Implement real phonemization (e.g. eSpeak-ng or custom rules)
        // For now, return text as-is or simple mapping to prevent crash
        return text
    }
}
