// App FASAS Signer per Android – PROTOTIPO NON COMPILATO NÉ COLLAUDATO in questo ambiente (manca l'SDK Android)
plugins {
    id("com.android.application") version "8.7.3"
    kotlin("android")
}

android {
    namespace = "it.fasas.signer.android"
    compileSdk = 34
    defaultConfig {
        applicationId = "it.fasas.signer.android"
        minSdk = 26          // java.util.Base64 e IsoDep con timeout estesi
        targetSdk = 34
        versionCode = 1
        versionName = "0.1-prototipo"
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
