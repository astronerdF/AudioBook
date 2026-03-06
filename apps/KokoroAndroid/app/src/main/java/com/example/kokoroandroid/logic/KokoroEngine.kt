package com.example.kokoroandroid.logic

import android.content.Context
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession

class KokoroEngine(private val context: Context) {
    private var ortEnv: OrtEnvironment? = null
    private var ortSession: OrtSession? = null
    private val phonemizer: Phonemizer = SimplePhonemizer()
    private val tokenizer = Tokenizer()
    private val voiceLoader = VoiceLoader(context)
    private var voices: Map<String, FloatArray> = emptyMap()

    fun initialize() {
        try {
            ortEnv = OrtEnvironment.getEnvironment()
            
            // Load model from assets
            val modelBytes = context.assets.open("kokoro.onnx").readBytes()
            ortSession = ortEnv?.createSession(modelBytes)
            
            // Load voices
            voices = voiceLoader.loadVoices("voices.bin")
            
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun generateAudio(text: String, voiceName: String = "af_heart"): FloatArray {
        if (ortSession == null) return FloatArray(0)

        // 1. Phonemize
        val phonemes = phonemizer.phonemize(text)
        
        // 2. Tokenize
        val inputIds = tokenizer.tokenize(phonemes)
        if (inputIds.isEmpty()) return FloatArray(0)
        
        // 3. Get Style
        val style = voices[voiceName] ?: voices.values.firstOrNull() ?: return FloatArray(0)
        
        // 4. Run Inference
        try {
            // Prepare inputs
            // Model expects:
            // tokens: int64 [1, seq_len]
            // style: float32 [1, 256]
            // speed: float32 [1]
            
            val tokensTensor = OnnxTensor.createTensor(ortEnv, arrayOf(inputIds))
            val styleTensor = OnnxTensor.createTensor(ortEnv, arrayOf(style))
            val speedTensor = OnnxTensor.createTensor(ortEnv, floatArrayOf(1.0f)) // Default speed
            
            val inputs = mapOf(
                "tokens" to tokensTensor,
                "style" to styleTensor,
                "speed" to speedTensor
            )
            
            val result = ortSession?.run(inputs)
            val outputTensor = result?.get(0) as? OnnxTensor
            val floatBuffer = outputTensor?.floatBuffer
            
            if (floatBuffer != null) {
                val audio = FloatArray(floatBuffer.remaining())
                floatBuffer.get(audio)
                return audio
            }
            
        } catch (e: Exception) {
            e.printStackTrace()
        }
        
        return FloatArray(0) 
    }

    fun close() {
        ortSession?.close()
        ortEnv?.close()
    }
}
