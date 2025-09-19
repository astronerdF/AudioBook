package com.audiobook.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TileMode
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.audiobook.app.R
import com.audiobook.app.data.PlayingState
import com.audiobook.app.data.SampleContent
import com.audiobook.app.ui.theme.ElectricLime
import com.audiobook.app.ui.theme.GlassBorder
import com.audiobook.app.ui.theme.GlassSurface
import com.audiobook.app.ui.theme.TextPrimary
import com.audiobook.app.ui.theme.TextSecondary
import com.audiobook.app.ui.theme.VioletSky

@Composable
fun HomeScreen(
    onSeeAllClicked: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .padding(horizontal = 20.dp)
            .padding(top = 64.dp, bottom = 88.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        GreetingHeader()
        SectionTitle(stringResource(id = R.string.home_continue_listening))
        ContinueListeningRow(items = SampleContent.continueListening)
        HighlightCard(onSeeAllClicked = onSeeAllClicked)
        FeaturedShelf()
    }
}

@Composable
private fun GreetingHeader() {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = "Good evening",
            color = TextSecondary,
            fontSize = 16.sp,
        )
        Text(
            text = "Find your next escape",
            color = TextPrimary,
            fontWeight = FontWeight.Bold,
            fontSize = 32.sp,
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ContinueListeningRow(items: List<PlayingState>) {
    LazyRow(
        horizontalArrangement = Arrangement.spacedBy(18.dp),
        contentPadding = PaddingValues(horizontal = 4.dp),
    ) {
        items(items, key = { it.bookTitle }) { item ->
            ContinueListeningCard(state = item)
        }
    }
}

@Composable
private fun ContinueListeningCard(state: PlayingState) {
    val shape = RoundedCornerShape(28.dp)
    Surface(
        modifier = Modifier
            .size(width = 220.dp, height = 160.dp)
            .clip(shape)
            .drawBehind {
                drawRect(color = Color.White.copy(alpha = 0.08f))
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(state.artworkColor, state.artworkColor.copy(alpha = 0f)),
                        tileMode = TileMode.Clamp,
                        radius = size.width,
                    ),
                )
            },
        color = GlassSurface,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(text = state.bookTitle, color = TextPrimary, fontWeight = FontWeight.SemiBold)
                Text(text = state.author, color = TextSecondary, fontSize = 12.sp)
            }
            ProgressArc(progress = state.progress, highlight = state.artworkColor)
            Text(text = state.durationLabel, color = TextSecondary, fontSize = 12.sp)
        }
    }
}

@Composable
private fun ProgressArc(progress: Float, highlight: Color) {
    androidx.compose.foundation.Canvas(modifier = Modifier.size(48.dp)) {
        val stroke = 6.dp.toPx()
        drawArc(
            color = Color.White.copy(alpha = 0.15f),
            startAngle = 140f,
            sweepAngle = 260f,
            useCenter = false,
            style = Stroke(width = stroke),
        )
        drawArc(
            brush = Brush.sweepGradient(listOf(highlight, ElectricLime)),
            startAngle = 140f,
            sweepAngle = 260f * progress,
            useCenter = false,
            style = Stroke(width = stroke),
        )
    }
}

@Composable
private fun HighlightCard(onSeeAllClicked: () -> Unit) {
    val shape = RoundedCornerShape(32.dp)
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Color.White.copy(alpha = 0.06f))
            .border(width = 1.dp, color = GlassBorder, shape = shape)
            .drawBehind {
                drawRect(
                    brush = Brush.verticalGradient(
                        colors = listOf(VioletSky.copy(alpha = 0.5f), Color.Transparent),
                    ),
                    alpha = 0.8f,
                )
            }
            .padding(24.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(
                text = "Immersive narratives",
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                fontSize = 24.sp,
            )
            Text(
                text = "Flow through curated collections tailored to your mood.",
                color = TextSecondary,
            )
            Button(
                onClick = onSeeAllClicked,
                colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent),
                border = BorderStroke(1.dp, ElectricLime.copy(alpha = 0.6f)),
            ) {
                Text(text = stringResource(id = R.string.home_see_all), color = ElectricLime)
            }
        }
    }
}

@Composable
private fun FeaturedShelf() {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(text = stringResource(id = R.string.home_recent_releases), color = TextPrimary, fontWeight = FontWeight.SemiBold)
            Icon(painter = painterResource(id = R.drawable.ic_nav_flow), contentDescription = null, tint = ElectricLime)
        }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            items(SampleContent.featured, key = { it.id }) { book ->
                FeaturedBookChip(title = book.title, author = book.author)
            }
        }
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(text = title, color = TextPrimary, fontWeight = FontWeight.SemiBold, fontSize = 20.sp)
}

@Composable
private fun FeaturedBookChip(title: String, author: String) {
    val shape = RoundedCornerShape(24.dp)
    Surface(
        modifier = Modifier
            .size(width = 160.dp, height = 200.dp)
            .clip(shape)
            .background(Color.White.copy(alpha = 0.04f))
            .border(width = 1.dp, color = GlassBorder.copy(alpha = 0.6f), shape = shape),
        color = Color.Transparent,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(Brush.linearGradient(listOf(VioletSky, ElectricLime))),
            )
            Spacer(modifier = Modifier.height(48.dp))
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(text = title, color = TextPrimary, fontWeight = FontWeight.Medium)
                Text(text = author, color = TextSecondary, fontSize = 12.sp)
            }
        }
    }
}
