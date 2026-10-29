package it.ipzs.cieidsdk.util

/**
 * Sostituisce il logger della libreria IAS di PagoPA/IPZS: nel FASAS Signer non si registrano mai APDU,
 * certificati o dati della carta (lo script fetch_ias.sh NON copia il logger originale).
 */
internal class CieIDSdkLogger {
    companion object {
        @Suppress("UNUSED_PARAMETER")
        fun log(message: String) = Unit
    }
}
