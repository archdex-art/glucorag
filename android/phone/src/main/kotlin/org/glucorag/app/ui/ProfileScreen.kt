package org.glucorag.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.glucorag.app.net.ProfileIn
import org.glucorag.shared.GlucoseUnit

/** A labelled group of radio buttons, with the reason the forecast needs it and an inline error. */
@Composable
private fun Choice(title: String, hint: String?, options: List<Pair<String, String>>, value: String?, error: String?, onChange: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        SectionTitle(title)
        Column(Modifier.selectableGroup()) {
            options.forEach { (key, label) ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .selectable(selected = value == key, role = Role.RadioButton, onClick = { onChange(key) })
                        .padding(vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = value == key, onClick = null)
                    Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 12.dp))
                }
            }
        }
        hint?.let { Hint(it) }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
    }
}

@Composable
private fun NumberField(value: String, onChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, error: String? = null, decimal: Boolean = true) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        isError = error != null,
        supportingText = error?.let { { Text(it) } },
        keyboardOptions = KeyboardOptions(keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number),
        modifier = modifier,
    )
}

/**
 * About you: the four facts the model reads (as on the website's set-up), and the glucose unit.
 * Saves with `PUT /me/profile`, then [onSaved].
 */
@Composable
fun ProfileScreen(onSaved: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val region = LocalConfiguration.current.locales[0]?.country
    var type by rememberSaveable { mutableStateOf<String?>(null) }
    var age by rememberSaveable { mutableStateOf("") }
    var sex by rememberSaveable { mutableStateOf<String?>(null) }
    var knowBmi by rememberSaveable { mutableStateOf(false) }
    var imperial by rememberSaveable { mutableStateOf(usesImperial(region)) }
    var bmiTyped by rememberSaveable { mutableStateOf("") }
    var cm by rememberSaveable { mutableStateOf("") }
    var kg by rememberSaveable { mutableStateOf("") }
    var ft by rememberSaveable { mutableStateOf("") }
    var inch by rememberSaveable { mutableStateOf("") }
    var lb by rememberSaveable { mutableStateOf("") }
    var unit by rememberSaveable { mutableStateOf(defaultGlucoseUnit(region).label) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var serverError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    val computed = when {
        knowBmi -> null
        imperial -> bmiImperial(parseNumber(ft), parseNumber(inch), parseNumber(lb))
        else -> bmiMetric(parseNumber(cm), parseNumber(kg))
    }
    val bmi = if (knowBmi) parseNumber(bmiTyped) else computed

    fun submit() {
        val ageN = age.trim().toIntOrNull()?.takeIf { it in 1..120 }
        val next = buildMap {
            if (type == null) put("type", "Choose type 1 or type 2.")
            if (ageN == null) put("age", "Enter your age in whole years, from 1 to 120.")
            if (sex == null) put("sex", "Choose female or male.")
            if (!bmiInRange(bmi)) {
                put(
                    "bmi",
                    if (knowBmi) "Enter a BMI from ${BMI_MIN.toInt()} to ${BMI_MAX.toInt()}, or work it out from your height and weight."
                    else "Enter your height and weight. They give a BMI of ${bmi?.let(::bmiText) ?: "—"}; it must be from ${BMI_MIN.toInt()} to ${BMI_MAX.toInt()}.",
                )
            }
        }
        errors = next
        serverError = null
        val t = type
        val s = sex
        if (next.isNotEmpty() || t == null || s == null || ageN == null || bmi == null) return
        busy = true
        scope.launch {
            val profile = ProfileIn(age = ageN, gender = s, bmi = round1(bmi), diabetesType = t, sensitivity = "standard", unit = unit)
            when (val r = Account.saveProfile(context, profile)) {
                is Account.Result.Ok -> onSaved()
                is Account.Result.Error -> serverError = r.message
            }
            busy = false
        }
    }

    Column(
        Modifier
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("About you", style = MaterialTheme.typography.headlineSmall)
        Hint("The forecast needs four facts about you: diabetes type, age, sex and body-mass index (BMI).")
        Sheet {
            Choice(
                "Diabetes type", "The model learned different glucose patterns for each type.",
                listOf("T1D" to "Type 1", "T2D" to "Type 2"), type, errors["type"],
            ) { type = it; errors = errors - "type" }
        }
        Sheet {
            SectionTitle("Age")
            NumberField(age, { age = it; errors = errors - "age" }, "Age in years", error = errors["age"], decimal = false)
            Hint("Glucose responses change with age.")
        }
        Sheet {
            Choice(
                "Sex", "The model was trained with sex recorded as female or male only, so those are the two choices.",
                listOf("F" to "Female", "M" to "Male"), sex, errors["sex"],
            ) { sex = it; errors = errors - "sex" }
        }
        Sheet {
            SectionTitle("Body-mass index (BMI)")
            val clearBmi = { errors = errors - "bmi" }
            if (knowBmi) {
                NumberField(bmiTyped, { bmiTyped = it; clearBmi() }, "BMI", Modifier.width(160.dp))
                TextButton(onClick = { knowBmi = false; clearBmi() }) { Text("Work it out from height and weight") }
            } else {
                if (imperial) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NumberField(ft, { ft = it; clearBmi() }, "Height, ft", Modifier.weight(1f), decimal = false)
                        NumberField(inch, { inch = it; clearBmi() }, "in", Modifier.weight(1f))
                    }
                    NumberField(lb, { lb = it; clearBmi() }, "Weight, lb", Modifier.width(160.dp))
                } else {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NumberField(cm, { cm = it; clearBmi() }, "Height, cm", Modifier.weight(1f))
                        NumberField(kg, { kg = it; clearBmi() }, "Weight, kg", Modifier.weight(1f))
                    }
                }
                Text("Your BMI: ${computed?.let(::bmiText) ?: "—"}", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { imperial = !imperial; clearBmi() }) {
                        Text(if (imperial) "Use cm and kg" else "Use feet and pounds")
                    }
                    TextButton(onClick = { knowBmi = true; clearBmi() }) { Text("I know my BMI") }
                }
            }
            Hint("Body size changes how glucose responds to food and insulin. The service accepts ${BMI_MIN.toInt()} to ${BMI_MAX.toInt()}.")
            errors["bmi"]?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
        }
        Sheet {
            Choice(
                "Glucose units", "Use the unit your meter or sensor shows. 100 mg/dL is 5.6 mmol/L.",
                GlucoseUnit.entries.map { it.label to it.label }, unit, null,
            ) { unit = it }
        }
        serverError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = ::submit, enabled = !busy) { Text(if (busy) "Saving" else "Save and continue") }
        ResearchNotice()
    }
}
