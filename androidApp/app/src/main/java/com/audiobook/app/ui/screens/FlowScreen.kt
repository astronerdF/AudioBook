package com.audiobook.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.audiobook.app.ui.theme.ElectricLime
import com.audiobook.app.ui.theme.GlassBorder
import com.audiobook.app.ui.theme.TextPrimary
import com.audiobook.app.ui.theme.TextSecondary
import com.audiobook.app.ui.theme.VioletSky

@Composable
fun FlowScreen(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 80.dp),
        verticalArrangement = Arrangement.spacedBy(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = "Daily Flow", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 28.sp)
        Text(
            text = "Set a vibe and we will string chapters together into a continuous mix.",
            color = TextSecondary,
            fontSize = 16.sp,
        )
        AuraDial()
        Button(
            onClick = { /* To be wired */ },
            colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent),
            border = androidx.compose.foundation.BorderStroke(1.dp, ElectricLime.copy(alpha = 0.8f)),
        ) {
            Text(text = "Start Flow", color = ElectricLime, fontSize = 16.sp)
        }
    }
}

@Composable
private fun AuraDial() {
    val shape = RoundedCornerShape(48.dp)
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(260.dp)
            .clip(shape)
            .background(Color.White.copy(alpha = 0.04f))
            .border(width = 1.dp, color = GlassBorder, shape = shape)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        colors = listOf(VioletSky.copy(alpha = 0.7f), ElectricLime.copy(alpha = 0.2f), Color.Transparent),
                    ),
                )
                .fillMaxSize(),
        )
        Text(text = "Chill", color = TextPrimary, fontSize = 40.sp, fontWeight = FontWeight.Light)
    }
}
