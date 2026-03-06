package com.example.kokoroandroid.logic

import android.content.Context
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipInputStream

class VoiceLoader(private val context: Context) {

    fun loadVoices(assetName: String): Map<String, FloatArray> {
        val voices = HashMap<String, FloatArray>()
        try {
            context.assets.open(assetName).use { inputStream ->
                ZipInputStream(inputStream).use { zipStream ->
                    var entry = zipStream.nextEntry
                    while (entry != null) {
                        if (entry.name.endsWith(".npy")) {
                            val voiceName = entry.name.removeSuffix(".npy")
                            val floatArray = parseNpy(zipStream)
                            if (floatArray != null) {
                                voices[voiceName] = floatArray
                            }
                        }
                        zipStream.closeEntry()
                        entry = zipStream.nextEntry
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return voices
    }

    private fun parseNpy(stream: InputStream): FloatArray? {
        // Simple NPY parser
        // Format:
        // Magic string: \x93NUMPY
        // Major version: 1 byte
        // Minor version: 1 byte
        // Header len: 2 bytes (little endian)
        // Header: JSON string describing shape and dtype
        // Data: Binary data

        try {
            val magic = ByteArray(6)
            if (stream.read(magic) != 6) return null
            // Verify magic? \x93NUMPY

            val version = ByteArray(2)
            stream.read(version)

            val headerLenBytes = ByteArray(2)
            stream.read(headerLenBytes)
            val headerLen = ByteBuffer.wrap(headerLenBytes).order(ByteOrder.LITTLE_ENDIAN).short.toInt()

            val headerBytes = ByteArray(headerLen)
            stream.read(headerBytes)
            // val header = String(headerBytes) 
            // We assume it's float32 and shape [1, 256] or similar. 
            // We just read the rest of the stream as floats.

            // Read data
            val bytes = stream.readBytes()
            val floatBuffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer()
            val floats = FloatArray(floatBuffer.remaining())
            floatBuffer.get(floats)
            return floats

        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }
}
