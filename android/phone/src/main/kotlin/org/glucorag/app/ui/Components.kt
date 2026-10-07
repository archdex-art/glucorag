package org.glucorag.app.ui

import android.content.Context
import android.content.Intent
import androidx.core.net.toUri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

const val RESEARCH_NOTICE = "Research prototype. Not a medical device. Don't use it to make treatment decisions."

/** One white sheet section, divided by hairline borders like the website. */
@Composable
fun Sheet(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = LocalGr.current
    Column(
        modifier
            .fillMaxWidth()
            .background(c.paper, RoundedCornerShape(8.dp))
            .border(1.dp, c.line, RoundedCornerShape(8.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )
}

@Composable
fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
}

@Composable
fun Hint(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, color = LocalGr.current.ink2)
}

@Composable
fun ResearchNotice(modifier: Modifier = Modifier) {
    Text(RESEARCH_NOTICE, style = MaterialTheme.typography.bodySmall, color = LocalGr.current.ink2, modifier = modifier)
}

/** The wall clock, ticking every [periodMs] while composed. */
@Composable
fun rememberNow(periodMs: Long = 30_000L): Long {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(periodMs) {
        while (true) {
            delay(periodMs)
            now = System.currentTimeMillis()
        }
    }
    return now
}

fun openUrl(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: android.content.ActivityNotFoundException) {
        // No browser: nothing to open.
    }
}
