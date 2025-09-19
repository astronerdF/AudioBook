package com.audiobook.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.audiobook.app.navigation.AudioBookDestination
import com.audiobook.app.navigation.AudioBookNavHost
import com.audiobook.app.ui.theme.AudioBookTheme
import com.audiobook.app.ui.theme.GlassBorder
import com.audiobook.app.ui.theme.TextSecondary
import com.audiobook.app.ui.theme.VioletSky
import com.audiobook.app.ui.theme.DeepTeal
import com.audiobook.app.ui.theme.Midnight
import com.audiobook.app.ui.theme.ElectricLime

@Composable
fun AudioBookApp() {
    AudioBookTheme {
        val navController = rememberNavController()
        val destinations = AudioBookDestination.bottomDestinations
        val navBackStackEntry by navController.currentBackStackEntryAsState()
        val currentDestination = navBackStackEntry?.destination?.route

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Color(0xFF06080F), DeepTeal.copy(alpha = 0.75f), Midnight),
                    ),
                )
                .background(
                    Brush.radialGradient(
                        colors = listOf(VioletSky.copy(alpha = 0.45f), Color.Transparent),
                        center = Offset(x = 600f, y = 0f),
                        radius = 1200f,
                    ),
                ),
        ) {
            Scaffold(
                containerColor = Color.Transparent,
                contentColor = Color.White,
                bottomBar = {
                    GlassyBottomBar(
                        destinations = destinations,
                        currentRoute = currentDestination,
                        onDestinationSelected = { route ->
                            if (route != currentDestination) {
                                navController.navigate(route) {
                                    launchSingleTop = true
                                    restoreState = true
                                    popUpTo(AudioBookDestination.Home.route) {
                                        saveState = true
                                    }
                                }
                            }
                        },
                    )
                },
            ) { innerPadding ->
                AudioBookNavHost(
                    navController = navController,
                    modifier = Modifier
                        .padding(innerPadding)
                        .fillMaxSize(),
                )
            }
        }
    }
}

@Composable
private fun GlassyBottomBar(
    destinations: List<AudioBookDestination>,
    currentRoute: String?,
    onDestinationSelected: (String) -> Unit,
) {
    val shape = RoundedCornerShape(32.dp)
    NavigationBar(
        modifier = Modifier
            .padding(horizontal = 16.dp, vertical = 18.dp)
            .clip(shape)
            .background(Color(0x19FFFFFF))
            .border(width = 1.dp, color = GlassBorder, shape = shape)
            .blur(24.dp),
        containerColor = Color.Transparent,
        tonalElevation = 0.dp,
        contentColor = Color.White,
    ) {
        destinations.forEach { destination ->
            val selected = destination.route == currentRoute
            NavigationBarItem(
                selected = selected,
                onClick = { onDestinationSelected(destination.route) },
                icon = {
                    Icon(
                        painter = painterResource(id = destination.icon),
                        contentDescription = stringResource(id = destination.label),
                        tint = if (selected) ElectricLime else TextSecondary,
                    )
                },
                label = { Text(text = stringResource(id = destination.label)) },
                alwaysShowLabel = false,
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = ElectricLime,
                    selectedTextColor = ElectricLime,
                    indicatorColor = Color(0x33FFFFFF),
                    unselectedIconColor = TextSecondary,
                    unselectedTextColor = TextSecondary,
                ),
            )
        }
    }
}
