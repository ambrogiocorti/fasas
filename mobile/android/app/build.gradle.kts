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
        // Nella CI il numero cresce a ogni compilazione (FASAS_VERSION_CODE): Android installa l'aggiornamento sopra
        // la versione precedente solo se il numero è più alto e la chiave di firma è la stessa.
        versionCode = System.getenv("FASAS_VERSION_CODE")?.toIntOrNull() ?: 3
        versionName = System.getenv("FASAS_VERSION_NAME") ?: "0.3"
    }
    // Firma di rilascio con la chiave della struttura: il file e le password arrivano da variabili d'ambiente (nella CI
    // dai segreti di GitHub) e non sono mai nel repository. Senza, si compila solo la versione di prova (debug).
    val keystore = System.getenv("FASAS_KEYSTORE_FILE")?.let { file(it) }?.takeIf { it.isFile }
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = keystore
                storePassword = System.getenv("FASAS_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("FASAS_KEY_ALIAS")
                keyPassword = System.getenv("FASAS_KEY_PASSWORD") ?: System.getenv("FASAS_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            // Niente offuscamento: la libreria della CIE usa la riflessione e il codice è comunque pubblico
            isMinifyEnabled = false
            if (keystore != null) signingConfig = signingConfigs.getByName("release")
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
