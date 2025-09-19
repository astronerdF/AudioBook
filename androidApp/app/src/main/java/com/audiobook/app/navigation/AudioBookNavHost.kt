package com.audiobook.app.navigation

import androidx.compose.animation.ExperimentalAnimationApi
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import com.audiobook.app.ui.screens.FlowScreen
import com.audiobook.app.ui.screens.HomeScreen
import com.audiobook.app.ui.screens.LibraryScreen
import com.audiobook.app.ui.screens.ProfileScreen
import com.google.accompanist.navigation.animation.AnimatedNavHost
import com.google.accompanist.navigation.animation.composable

@OptIn(ExperimentalAnimationApi::class)
@Composable
fun AudioBookNavHost(
    navController: NavHostController,
    modifier: Modifier = Modifier,
) {
    AnimatedNavHost(
        navController = navController,
        startDestination = AudioBookDestination.Home.route,
        modifier = modifier,
        enterTransition = { slideInHorizontally { it / 3 } + fadeIn() },
        exitTransition = { fadeOut() },
        popEnterTransition = { fadeIn() },
        popExitTransition = { slideOutHorizontally { -it / 3 } + fadeOut() },
    ) {
        composable(AudioBookDestination.Home.route) {
            HomeScreen(onSeeAllClicked = { navController.navigate(AudioBookDestination.Library.route) })
        }
        composable(AudioBookDestination.Library.route) {
            LibraryScreen()
        }
        composable(AudioBookDestination.Flow.route) {
            FlowScreen()
        }
        composable(AudioBookDestination.Profile.route) {
            ProfileScreen()
        }
    }
}
