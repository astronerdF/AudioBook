package com.example.kokoroandroid.logic

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log

class SimpleAudioPlayer {
    private var audioTrack: AudioTrack? = null
    private val SAMPLE_RATE = 24000 // Kokoro usually outputs 24kHz

    fun play(audioData: FloatArray) {
        if (audioData.isEmpty()) return

        try {
            val bufferSize = AudioTrack.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_FLOAT
            )

            val audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()

            val format = AudioFormat.Builder()
                .setSampleRate(SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                .build()

            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(audioAttributes)
                .setAudioFormat(format)
                .setBufferSizeInBytes(maxOf(bufferSize, audioData.size * 4))
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()

            audioTrack?.write(audioData, 0, audioData.size, AudioTrack.WRITE_BLOCKING)
            audioTrack?.play()
            
        } catch (e: Exception) {
            Log.e("AudioPlayer", "Error playing audio", e)
        }
    }

    fun release() {
        audioTrack?.release()
        audioTrack = null
    }
}
