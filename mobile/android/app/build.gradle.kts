// App FASAS Signer per Android – PROTOTIPO NON COMPILATO NÉ COLLAUDATO in questo ambiente (manca l'SDK Android)
plugins {
    id("com.android.application")   // versione nel build.gradle.kts principale
    kotlin("android")
}

android {
    namespace = "it.fasas.signer.android"
    compileSdk = 34
    defaultConfig {
        applicationId = "it.fasas.signer.android"
        minSdk = 26          // java.util.Base64 e IsoDep con timeout estesi
        targetSdk = 34
        versionCode = 2
        versionName = "0.2-prova"
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation(project(":signer-core"))
}

// Schermate dell'app (chiaro e scuro) disegnate da Paparazzi senza telefono né emulatore, per controllarne l'aspetto:
//   FASAS_SCREENSHOTS=1 gradle :app:recordPaparazziDebug   → app/src/test/snapshots/images/
if (System.getenv("FASAS_SCREENSHOTS") == "1") {
    apply(plugin = "app.cash.paparazzi")
    android.sourceSets.getByName("test").java.srcDir("src/screenshots/kotlin")
}
