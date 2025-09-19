package com.audiobook.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color

private val DarkPalette = darkColorScheme(
    primary = ElectricLime,
    onPrimary = Midnight,
    secondary = VioletSky,
    background = Midnight,
    onBackground = TextPrimary,
    surface = GlassSurface,
    onSurface = TextPrimary,
)

private val LightPalette = lightColorScheme(
    primary = VioletSky,
    onPrimary = Midnight,
    secondary = ElectricLime,
    background = Color(0xFFF7F8FB),
    onBackground = Color(0xFF10131A),
    surface = Color(0xAAFFFFFF),
    onSurface = Color(0xFF10131A),
)

@Composable
fun AudioBookTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colorScheme: ColorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkPalette
        else -> LightPalette
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content,
    )
}
