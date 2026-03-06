package com.example.kokoroandroid.logic

class Tokenizer {
    private val PAD = "$"
    private val PUNCTUATION = ";:,.!?¡¿—…\"«»“” "
    private val LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    private val IPA = "ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶʘɹɺɾɻʀʁɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑʼʴʰʱʲʷˠˤ˞↓↑→↗↘'̩'ᵻ"

    private val vocab = PAD + PUNCTUATION + LETTERS + IPA
    private val charToId = vocab.withIndex().associate { it.value to it.index }

    fun tokenize(text: String): LongArray {
        // TODO: This assumes the input text is ALREADY phonemized or contains valid vocab chars.
        // If the Phonemizer returns raw text, we will map what we can and ignore the rest.
        
        val ids = ArrayList<Long>()
        // Always start with PAD? Some implementations do. Let's stick to simple mapping first.
        
        for (char in text) {
            val id = charToId[char]
            if (id != null) {
                ids.add(id.toLong())
            } else {
                // Handle unknown chars (maybe map to space or ignore)
                // For now, ignore.
            }
        }
        return ids.toLongArray()
    }
}
