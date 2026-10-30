// Plugin Kotlin e Android nello stesso classloader (quello del progetto radice). Il plugin Android si carica solo
// dove c'è l'SDK Android (Android Studio o ANDROID_HOME, come nella CI): altrove si compila solo signer-core.
buildscript {
    val hasAndroidSdk = System.getenv("ANDROID_HOME") != null || file("local.properties").exists()
    repositories {
        google()
        maven("https://maven-central.storage-download.googleapis.com/maven2/")
        mavenCentral()
        gradlePluginPortal()
    }
    dependencies {
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.0.21")
        if (hasAndroidSdk) classpath("com.android.tools.build:gradle:8.7.3")
    }
}
