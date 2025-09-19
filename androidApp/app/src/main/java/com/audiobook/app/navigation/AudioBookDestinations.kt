package com.audiobook.app.navigation

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import com.audiobook.app.R

sealed class AudioBookDestination(
    val route: String,
    @StringRes val label: Int,
    @DrawableRes val icon: Int,
) {
    data object Home : AudioBookDestination(
        route = "home",
        label = R.string.nav_home,
        icon = R.drawable.ic_nav_home,
    )

    data object Library : AudioBookDestination(
        route = "library",
        label = R.string.nav_library,
        icon = R.drawable.ic_nav_library,
    )

    data object Flow : AudioBookDestination(
        route = "flow",
        label = R.string.nav_flow,
        icon = R.drawable.ic_nav_flow,
    )

    data object Profile : AudioBookDestination(
        route = "profile",
        label = R.string.nav_profile,
        icon = R.drawable.ic_nav_profile,
    )

    companion object {
        val bottomDestinations = listOf(Home, Library, Flow, Profile)
    }
}
