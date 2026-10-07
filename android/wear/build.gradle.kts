plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "org.glucorag.wear"
    compileSdk = 37

    defaultConfig {
        // Same applicationId as :phone: the Wearable Data Layer only pairs apps with the same
        // package name and signing certificate.
        applicationId = "org.glucorag.app"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        // Development-only key shared with :phone (see keystore/README.md).
        getByName("debug") {
            storeFile = rootProject.file("keystore/glucorag-dev.jks")
            storePassword = "glucorag-dev"
            keyAlias = "glucorag"
            keyPassword = "glucorag-dev"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(project(":shared"))

    implementation(platform(libs.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.wear.compose.material3)
    implementation(libs.androidx.wear)
    implementation(libs.protolayout)
    implementation(libs.protolayout.material3)
    implementation(libs.tiles)
    implementation(libs.complications.datasource)
    implementation(libs.androidx.work.runtime)
    implementation(libs.play.services.wearable)
    implementation(libs.datastore.preferences)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)

    testImplementation(libs.junit)
}
