package com.example.kokoroandroid.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import com.example.kokoroandroid.model.Book
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipFile
import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserFactory

class EpubParser(private val context: Context) {

    fun parseEpub(file: File): Book? {
        try {
            ZipFile(file).use { zip ->
                // 1. Find OPF file path from META-INF/container.xml
                val containerEntry = zip.getEntry("META-INF/container.xml") ?: return null
                val containerXml = zip.getInputStream(containerEntry).bufferedReader().use { it.readText() }
                val opfPath = extractOpfPath(containerXml) ?: return null

                // 2. Parse OPF file for metadata
                val opfEntry = zip.getEntry(opfPath) ?: return null
                val opfXml = zip.getInputStream(opfEntry).bufferedReader().use { it.readText() }
                val metadata = extractMetadata(opfXml)
                
                // 3. Extract Cover
                var coverUri: String? = null
                if (metadata.coverId != null) {
                    val coverHref = extractCoverHref(opfXml, metadata.coverId)
                    if (coverHref != null) {
                        // Resolve relative path
                        val opfDir = File(opfPath).parent ?: ""
                        val coverPath = if (opfDir.isNotEmpty()) "$opfDir/$coverHref" else coverHref
                        
                        val coverEntry = zip.getEntry(coverPath)
                        if (coverEntry != null) {
                            val coverBitmap = BitmapFactory.decodeStream(zip.getInputStream(coverEntry))
                            coverUri = saveCoverToCache(coverBitmap, file.nameWithoutExtension)
                        }
                    }
                }

                return Book(
                    id = file.nameWithoutExtension, // Simple ID for now
                    title = metadata.title ?: file.nameWithoutExtension,
                    author = metadata.author ?: "Unknown Author",
                    coverUri = coverUri,
                    filePath = file.absolutePath
                )
            }
        } catch (e: Exception) {
            Log.e("EpubParser", "Error parsing ${file.name}", e)
            return null
        }
    }

    private data class EpubMetadata(val title: String?, val author: String?, val coverId: String?)

    private fun extractOpfPath(containerXml: String): String? {
        // Simple regex extraction to avoid full XML parsing overhead for this small file
        val regex = "full-path=\"([^\"]+)\"".toRegex()
        return regex.find(containerXml)?.groupValues?.get(1)
    }

    private fun extractMetadata(opfXml: String): EpubMetadata {
        var title: String? = null
        var author: String? = null
        var coverId: String? = null

        try {
            val factory = XmlPullParserFactory.newInstance()
            val parser = factory.newPullParser()
            parser.setInput(opfXml.reader())

            var eventType = parser.eventType
            while (eventType != XmlPullParser.END_DOCUMENT) {
                if (eventType == XmlPullParser.START_TAG) {
                    when (parser.name) {
                        "dc:title" -> title = parser.nextText()
                        "dc:creator" -> author = parser.nextText()
                        "meta" -> {
                            val name = parser.getAttributeValue(null, "name")
                            val content = parser.getAttributeValue(null, "content")
                            if (name == "cover") {
                                coverId = content
                            }
                        }
                    }
                }
                eventType = parser.next()
            }
        } catch (e: Exception) {
            Log.e("EpubParser", "XML parsing error", e)
        }
        return EpubMetadata(title, author, coverId)
    }

    private fun extractCoverHref(opfXml: String, coverId: String): String? {
         try {
            val factory = XmlPullParserFactory.newInstance()
            val parser = factory.newPullParser()
            parser.setInput(opfXml.reader())

            var eventType = parser.eventType
            while (eventType != XmlPullParser.END_DOCUMENT) {
                if (eventType == XmlPullParser.START_TAG && parser.name == "item") {
                    val id = parser.getAttributeValue(null, "id")
                    if (id == coverId) {
                        return parser.getAttributeValue(null, "href")
                    }
                }
                eventType = parser.next()
            }
        } catch (e: Exception) {
             Log.e("EpubParser", "XML parsing error for cover href", e)
        }
        return null
    }

    private fun saveCoverToCache(bitmap: Bitmap, bookId: String): String {
        val cacheDir = File(context.cacheDir, "covers")
        if (!cacheDir.exists()) cacheDir.mkdirs()
        val file = File(cacheDir, "$bookId.jpg")
        FileOutputStream(file).use { out ->
            bitmap.compress(Bitmap.CompressFormat.JPEG, 90, out)
        }
        return file.absolutePath
    }
}
