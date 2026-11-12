// Protocollo FASAS Sign e flusso di firma: Kotlin puro, usato dall'app Android e collaudabile sulla JVM
plugins { kotlin("jvm") }

dependencies {
    compileOnly("org.json:json:20240303")       // su Android org.json è già nella piattaforma
    testImplementation("org.json:json:20240303")
    testImplementation(kotlin("test"))
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

tasks.test {
    useJUnitPlatform()
    // Collaudo contro un FASAS in esecuzione (facoltativo): vedi README.md
    listOf("FASAS_TEST_SERVER", "FASAS_TEST_PAIRING_CODE", "FASAS_TEST_KEY", "FASAS_TEST_CERT")
        .forEach { name -> System.getenv(name)?.let { environment(name, it) } }
}
