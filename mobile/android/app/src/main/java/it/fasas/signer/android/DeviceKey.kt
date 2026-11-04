package it.fasas.signer.android

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Chiave della verifica con impronta, volto o PIN del telefono (solo per aprire i documenti, non per firmarli):
 * EC P-256 creata nel chip sicuro del telefono (Keystore Android, StrongBox se c'è), non esportabile e usabile solo
 * subito dopo lo sblocco da parte dell'utente. Il FASAS ne riceve solo la chiave pubblica; impronta, volto e PIN
 * restano al telefono. Se sul telefono si aggiunge una nuova impronta la chiave si invalida e se ne crea un'altra.
 */
object DeviceKey {
    private const val ALIAS = "fasas-verifica-identita"

    /** BiometricPrompt con chiave crittografica: da Android 9. */
    val supported get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P

    private fun store() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    fun exists() = store().containsAlias(ALIAS)

    fun delete() = runCatching { store().deleteEntry(ALIAS) }

    /** Crea la chiave se manca e restituisce la chiave pubblica (X.509 DER) da registrare sul FASAS. */
    fun publicKey(): ByteArray {
        val keys = store()
        if (!keys.containsAlias(ALIAS)) generate()
        return keys.getCertificate(ALIAS).publicKey.encoded
    }

    private fun spec(strongBox: Boolean): KeyGenParameterSpec {
        val builder = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
            .setInvalidatedByBiometricEnrollment(true)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // ogni uso richiede lo sblocco: impronta/volto (classe «forte») oppure PIN, segno o password del telefono
            builder.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL)
        } else {
            @Suppress("DEPRECATION")
            builder.setUserAuthenticationValidityDurationSeconds(-1)  // Android 9-10: solo impronta o volto, a ogni uso
        }
        if (strongBox && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) builder.setIsStrongBoxBacked(true)
        return builder.build()
    }

    private fun generate() {
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        try {
            generator.initialize(spec(strongBox = true))
            generator.generateKeyPair()
        } catch (e: StrongBoxUnavailableException) {
            generator.initialize(spec(strongBox = false))
            generator.generateKeyPair()
        }
    }

    /** Firma da sbloccare con BiometricPrompt; null se la chiave è stata invalidata (nuova impronta sul telefono). */
    fun signature(): Signature? = try {
        val key = store().getKey(ALIAS, null) as? PrivateKey ?: return null
        Signature.getInstance("SHA256withECDSA").apply { initSign(key) }
    } catch (e: KeyPermanentlyInvalidatedException) {
        null
    }
}
