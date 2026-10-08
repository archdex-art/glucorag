plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
}

android {
    namespace = "org.glucorag.app"
    compileSdk = 37

    defaultConfig {
        // Same applicationId as :wear: the Wearable Data Layer only pairs apps with the same
        // package name and signing certificate.
        applicationId = "org.glucorag.app"
        minSdk = 28
        targetSdk = 36
        versionCode = 3
        versionName = "0.3.0"
        // ONNX Runtime ships ~30 MB of native code per ABI. Phones (and the Apple-silicon
        // emulator) are ARM; x86 emulator images aren't supported.
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    // Compress native libraries in the APK (extracted on install): the download is far smaller.
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }

    signingConfigs {
        // Development-only key shared with :wear (see keystore/README.md).
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
        release {
            signingConfig = signingConfigs.getByName("debug")
            isMinifyEnabled = false
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
    // The Compose compiler plugin needs the Compose runtime on the classpath once sources exist.
    implementation(platform(libs.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)
    implementation(libs.datastore.preferences)
    implementation(libs.androidx.work.runtime)
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.play.services.wearable)
    // Google's code scanner: Play services shows the camera, so the app needs no camera permission.
    implementation(libs.play.services.code.scanner)
    // Runs the forecast model (assets/model/model.onnx) on the phone.
    implementation(libs.onnxruntime.android)

    testImplementation(libs.junit)
    testImplementation(libs.mockwebserver3)
    testImplementation(libs.onnxruntime.jvm)
}

// JVM unit tests can't load the Android natives: they run the same API from the desktop build.
configurations.configureEach {
    if (name.endsWith("UnitTestRuntimeClasspath")) {
        exclude(group = "com.microsoft.onnxruntime", module = "onnxruntime-android")
    }
}
