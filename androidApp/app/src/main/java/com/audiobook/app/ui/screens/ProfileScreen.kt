package com.audiobook.app.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Divider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.vectorResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.audiobook.app.R
import com.audiobook.app.ui.theme.TextPrimary
import com.audiobook.app.ui.theme.TextSecondary

@Composable
fun ProfileScreen(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .padding(horizontal = 24.dp, vertical = 80.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            Image(
                modifier = Modifier
                    .size(72.dp)
                    .clip(CircleShape)
                    .background(Color.White.copy(alpha = 0.08f)),
                imageVector = ImageVector.vectorResource(id = R.drawable.ic_nav_profile),
                contentDescription = null,
            )
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(text = "Hey there, Ade!", color = TextPrimary, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(text = "19 hours listened this week", color = TextSecondary)
            }
        }
        Divider(color = Color.White.copy(alpha = 0.08f))
        Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
            ProfileRow(label = "Listening stats", value = "Top 5% of listeners")
            ProfileRow(label = "Preferred vibe", value = "Atmospheric, Calm")
            ProfileRow(label = "Downloads", value = "12 titles on device")
        }
    }
}

@Composable
private fun ProfileRow(label: String, value: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(text = label.uppercase(), color = TextSecondary, fontSize = 12.sp)
        Text(text = value, color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
    }
}
