package org.glucorag.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import org.glucorag.app.R
import org.glucorag.shared.Zone

/** The website's colour tokens (web/src/styles/tokens.css), light and dark. */
data class GrColors(
    val ground: Color,
    val paper: Color,
    val wash: Color,
    val line: Color,
    val ink: Color,
    val ink2: Color,
    val action: Color,
    val onAction: Color,
    val bandOuter: Color,
    val bandInner: Color,
    val zoneFill: Map<Zone, Color>,
    val zoneText: Map<Zone, Color>,
    val zoneTint: Map<Zone, Color>,
)

private val Light = GrColors(
    ground = Color(0xFFEEF2F6), paper = Color(0xFFFFFFFF), wash = Color(0xFFF5F8FB), line = Color(0xFFDCE3EB),
    ink = Color(0xFF0E2742), ink2 = Color(0xFF4A6079), action = Color(0xFF1D5FA8), onAction = Color(0xFFFFFFFF),
    bandOuter = Color(0xFFD6E4F4), bandInner = Color(0xFF5B8FCB),
    zoneFill = mapOf(
        Zone.VERY_LOW to Color(0xFF8E1B1B), Zone.LOW to Color(0xFFD7372A), Zone.TARGET to Color(0xFF3C9A55),
        Zone.HIGH to Color(0xFFF0C232), Zone.VERY_HIGH to Color(0xFFE8772E),
    ),
    zoneText = mapOf(
        Zone.VERY_LOW to Color(0xFF7A1616), Zone.LOW to Color(0xFFB3261E), Zone.TARGET to Color(0xFF1E6B35),
        Zone.HIGH to Color(0xFF7A5900), Zone.VERY_HIGH to Color(0xFF9E430E),
    ),
    zoneTint = mapOf(
        Zone.VERY_LOW to Color(0xFFF7E3E3), Zone.LOW to Color(0xFFFCEAE7), Zone.TARGET to Color(0xFFE9F5EC),
        Zone.HIGH to Color(0xFFFDF5D7), Zone.VERY_HIGH to Color(0xFFFCEADE),
    ),
)

private val Dark = GrColors(
    ground = Color(0xFF0B1625), paper = Color(0xFF102136), wash = Color(0xFF15293F), line = Color(0xFF22364D),
    ink = Color(0xFFE6EDF5), ink2 = Color(0xFFA7B8CB), action = Color(0xFF7EB0EC), onAction = Color(0xFF0B1625),
    bandOuter = Color(0xFF1C324C), bandInner = Color(0xFF4F86C8),
    zoneFill = mapOf(
        Zone.VERY_LOW to Color(0xFFE0605C), Zone.LOW to Color(0xFFF07A6E), Zone.TARGET to Color(0xFF5CC27A),
        Zone.HIGH to Color(0xFFE8C24A), Zone.VERY_HIGH to Color(0xFFF09A5A),
    ),
    zoneText = mapOf(
        Zone.VERY_LOW to Color(0xFFFF9A94), Zone.LOW to Color(0xFFFFA49B), Zone.TARGET to Color(0xFF8FDCA6),
        Zone.HIGH to Color(0xFFF2D27A), Zone.VERY_HIGH to Color(0xFFFFB988),
    ),
    zoneTint = mapOf(
        Zone.VERY_LOW to Color(0xFF271D29), Zone.LOW to Color(0xFF29202B), Zone.TARGET to Color(0xFF132A2F),
        Zone.HIGH to Color(0xFF252823), Zone.VERY_HIGH to Color(0xFF272324),
    ),
)

val LocalGr = staticCompositionLocalOf { Light }

private val Atkinson = FontFamily(
    Font(R.font.atkinson_hyperlegible_next, FontWeight.Normal),
    Font(R.font.atkinson_hyperlegible_next, FontWeight.SemiBold),
    Font(R.font.atkinson_hyperlegible_next, FontWeight.Bold),
)

private fun typography(): Typography {
    val base = Typography()
    fun TextStyle.a() = copy(fontFamily = Atkinson)
    return Typography(
        displaySmall = base.displaySmall.a().copy(fontWeight = FontWeight.Bold),
        headlineSmall = base.headlineSmall.a().copy(fontWeight = FontWeight.SemiBold, fontSize = 24.sp),
        titleMedium = base.titleMedium.a().copy(fontWeight = FontWeight.SemiBold),
        titleSmall = base.titleSmall.a().copy(fontWeight = FontWeight.SemiBold),
        bodyLarge = base.bodyLarge.a(),
        bodyMedium = base.bodyMedium.a(),
        bodySmall = base.bodySmall.a(),
        labelLarge = base.labelLarge.a().copy(fontWeight = FontWeight.SemiBold),
        labelMedium = base.labelMedium.a(),
    )
}

@Composable
fun GlucoTheme(content: @Composable () -> Unit) {
    val c = if (isSystemInDarkTheme()) Dark else Light
    val scheme = if (isSystemInDarkTheme()) {
        darkColorScheme(
            primary = c.action, onPrimary = c.onAction, background = c.ground, onBackground = c.ink,
            surface = c.paper, onSurface = c.ink, onSurfaceVariant = c.ink2, outline = c.line, surfaceVariant = c.wash,
        )
    } else {
        lightColorScheme(
            primary = c.action, onPrimary = c.onAction, background = c.ground, onBackground = c.ink,
            surface = c.paper, onSurface = c.ink, onSurfaceVariant = c.ink2, outline = c.line, surfaceVariant = c.wash,
        )
    }
    CompositionLocalProvider(LocalGr provides c) {
        MaterialTheme(colorScheme = scheme, typography = typography(), content = content)
    }
}
