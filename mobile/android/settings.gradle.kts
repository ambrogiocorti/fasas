// FASAS Signer per Android – PROTOTIPO NON COLLAUDATO con una CIE reale (vedi README.md)
pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        // Mirror di Maven Central (Google): utile quando repo.maven.apache.org limita le richieste
        maven("https://maven-central.storage-download.googleapis.com/maven2/")
        mavenCentral()
    }
}
rootProject.name = "fasas-signer-android"
include(":signer-core")
// Il modulo dell'app richiede l'SDK Android (Android Studio o ANDROID_HOME)
val hasAndroidSdk = System.getenv("ANDROID_HOME") != null || file("local.properties").exists()
if (hasAndroidSdk) include(":app")
