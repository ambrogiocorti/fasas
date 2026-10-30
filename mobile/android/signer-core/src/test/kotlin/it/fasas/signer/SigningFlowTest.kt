package it.fasas.signer

import java.io.File
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.PKCS8EncodedKeySpec
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * Carta software SOLO PER TEST: chiave RSA di prova in memoria, PIN fisso. Serve a collaudare il protocollo
 * del telefono contro un FASAS vero; non sostituisce il collaudo con una CIE reale via NFC.
 */
class SoftwareTestSession(private val key: PrivateKey, private val cert: ByteArray, private val pin: String) : CieSession {
    var attemptsLeft = 3
    override fun open(pin: String) {
        if (pin != this.pin) {
            attemptsLeft -= 1
            throw if (attemptsLeft == 0) CardException("pin_blocked", "PIN bloccato.", 0)
            else CardException("pin_wrong", "PIN errato.", attemptsLeft)
        }
        attemptsLeft = 3
    }

    override fun readCertificate() = cert

    override fun signDigestInfo(digestInfo: ByteArray): ByteArray =
        Signature.getInstance("NONEwithRSA").run { initSign(key); update(digestInfo); sign() }
}

class SigningFlowTest {
    @Test
    fun httpIsRefusedForRemoteServers() {
        assertFailsWith<IllegalArgumentException> { FasasApi("http://fasas.esempio.it/") }
        assertFailsWith<IllegalArgumentException> { FasasApi("http://fasas.esempio.it/", allowLanHttp = true) }
        assertFailsWith<IllegalArgumentException> { FasasApi("http://192.168.1.20:8000/") }
        assertFailsWith<IllegalArgumentException> { FasasApi("http://8.8.8.8:8000/", allowLanHttp = true) }
        FasasApi("http://192.168.1.20:8000/", allowLanHttp = true)
        FasasApi("http://10.0.0.5:8000/", allowLanHttp = true)
        FasasApi("http://172.20.1.2:8000/", allowLanHttp = true)
        FasasApi("https://fasas.esempio.it/")
        FasasApi("http://127.0.0.1:8000/")
    }

    @Test
    fun digestInfoPrefixIsSha256() {
        val digest = MessageDigest.getInstance("SHA-256").digest("x".toByteArray())
        val info = SigningFlow.SHA256_DIGEST_INFO_PREFIX + digest
        assertEquals(51, info.size)
        assertEquals("3031300d060960864801650304020105000420",
            SigningFlow.SHA256_DIGEST_INFO_PREFIX.joinToString("") { "%02x".format(it) })
    }

    /** Collaudo contro un FASAS in esecuzione: richiede FASAS_TEST_SERVER, _PAIRING_CODE, _KEY (PKCS#8 DER), _CERT (DER). */
    @Test
    fun signsAgainstRunningFasas() {
        val server = System.getenv("FASAS_TEST_SERVER") ?: return println("FASAS_TEST_SERVER non impostato: collaudo saltato")
        val key = KeyFactory.getInstance("RSA").generatePrivate(PKCS8EncodedKeySpec(File(System.getenv("FASAS_TEST_KEY")).readBytes()))
        val session = SoftwareTestSession(key, File(System.getenv("FASAS_TEST_CERT")).readBytes(), "12345678")
        val api = FasasApi(server)
        api.pair(System.getenv("FASAS_TEST_PAIRING_CODE"), "Telefono di prova (JVM)")
        val requests = api.pending(wait = 5)
        assertTrue(requests.isNotEmpty(), "nessuna richiesta di firma in attesa sul FASAS")
        val request = requests.first()
        val flow = SigningFlow(api)
        flow.accept(request)
        assertIs<Outcome.PinWrong>(flow.onCard(request, session, "00000000")).also { assertEquals(2, it.attemptsLeft) }
        val outcome = flow.onCard(request, session, "12345678")
        assertIs<Outcome.Signed>(outcome, outcome.toString())
        println("Esito: $outcome")
    }
}
