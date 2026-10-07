package org.glucorag.wear.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.foundation.rotary.RotaryScrollableDefaults
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text

/** First launch: the one-time research-prototype notice. */
@Composable
fun AcknowledgeScreen(onAcknowledge: () -> Unit) {
    val listState = rememberScalingLazyListState()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        ScalingLazyColumn(
            modifier = Modifier.fillMaxWidth(),
            state = listState,
            contentPadding = contentPadding,
            horizontalAlignment = Alignment.CenterHorizontally,
            rotaryScrollableBehavior = RotaryScrollableDefaults.behavior(listState),
        ) {
            item {
                Text(
                    RESEARCH_NOTICE,
                    style = MaterialTheme.typography.bodyLarge,
                    color = Colors.Ink,
                    textAlign = TextAlign.Center,
                )
            }
            item {
                Button(onClick = onAcknowledge, modifier = Modifier.fillMaxWidth()) {
                    Text("I understand")
                }
            }
        }
    }
}
