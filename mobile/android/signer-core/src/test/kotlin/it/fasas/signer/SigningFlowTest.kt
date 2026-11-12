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

/** FASAS finto in memoria (stessi passi e nonce del server vero) per provare il flusso senza rete né carta. */
class FakeFasas : AutoCloseable {
    private val server = com.sun.net.httpserver.HttpServer.create(java.net.InetSocketAddress("127.0.0.1", 0), 0)
    private var nonce = "n0"
    private var counter = 0
    val calls = mutableListOf<String>()
    val nisBodies = mutableListOf<org.json.JSONObject>()
    lateinit var publicKey: java.security.PublicKey
    val toBeSigned = "attributi firmati di prova".toByteArray()
    var signedOk = false
    val url get() = "http://127.0.0.1:${server.address.port}/"

    init {
        server.createContext("/api/firma/v1/") { ex ->
            val path = ex.requestURI.path.removePrefix("/api/firma/v1/")
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8).let { if (it.isBlank()) org.json.JSONObject() else org.json.JSONObject(it) }
            val step = path.split("/").getOrElse(2) { "" }
            calls += step
            val reply = org.json.JSONObject()
            var status = 200
            if (step != "prendi" && body.optString("nonce") != nonce) {
                status = 409; reply.put("error", "bad_nonce").put("message", "nonce errato")
            } else {
                nonce = "n${++counter}"
                reply.put("nonce", nonce)
                when (step) {
                    "prendi" -> reply.put("verify_code", "ABCD-EFGH").put("challenge", Base64Codec.encode(toBeSigned.copyOf(16)))
                    "cie-senza-pin" -> {
                        nisBodies += body
                        if (body.optString("pin") != "482913") {
                            nonce = body.getString("nonce")  // PIN errato: la richiesta resta allo stesso passo
                            status = 400
                            reply.put("error", "pin_wrong").put("message", "PIN FASAS errato.").put("attempts_left", 4)
                        } else {
                            reply.put("verification", org.json.JSONObject().put("level", "Verifica di identità"))
                        }
                    }
                    "certificato" -> {
                        val digest = MessageDigest.getInstance("SHA-256").digest(toBeSigned)
                        reply.put("to_be_signed", Base64Codec.encode(toBeSigned))
                            .put("digest_info", Base64Codec.encode(SigningFlow.SHA256_DIGEST_INFO_PREFIX + digest))
                            .put("verify_code", "ABCD-EFGH")
                    }
                    "firma" -> {
                        val ok = Signature.getInstance("SHA256withRSA").run {
                            initVerify(publicKey); update(toBeSigned); verify(Base64Codec.decode(body.getString("signature")))
                        }
                        signedOk = ok
                        reply.put("verification", org.json.JSONObject().put("level", "PAdES-B-B"))
                    }
                }
            }
            val bytes = reply.toString().toByteArray()
            ex.sendResponseHeaders(status, bytes.size.toLong())
            ex.responseBody.use { it.write(bytes) }
        }
        server.start()
    }

    override fun close() = server.stop(0)
}

/** Carta che si allontana la prima volta che le si chiede di firmare. */
class SlippingSession(private val inner: SoftwareTestSession) : CieSession by inner {
    var slips = 1
    override fun signDigestInfo(digestInfo: ByteArray): ByteArray {
        if (slips-- > 0) throw CardException("card_removed", "La carta è stata allontanata dal telefono.")
        return inner.signDigestInfo(digestInfo)
    }
}

class CardMovedTest {
    @Test
    fun resumesAfterTheCardIsMoved() {
        val pair = java.security.KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.genKeyPair()
        FakeFasas().use { fake ->
            fake.publicKey = pair.public
            val flow = SigningFlow(FasasApi(fake.url))
            val request = SignRequest("r1", "Documento", 1, "00", "ABCD-EFGH", "")
            flow.accept(request)
            val session = SlippingSession(SoftwareTestSession(pair.private, byteArrayOf(1, 2, 3), "12345678"))
            assertIs<Outcome.CardMoved>(flow.onCard(request, session, "12345678"))
            val outcome = flow.onCard(request, session, "12345678")
            assertIs<Outcome.Signed>(outcome, outcome.toString())
            assertTrue(fake.signedOk)
            // certificato inviato una volta sola, nessun errore segnalato al server: la richiesta è proseguita
            assertEquals(listOf("prendi", "stato", "certificato", "stato", "firma"), fake.calls)
        }
    }

    @Test
    fun cardWithoutItsPinAndFasasPin() {
        FakeFasas().use { fake ->
            val flow = SigningFlow(FasasApi(fake.url))
            val request = SignRequest("r3", "Relazione", null, "00", "ABCD-EFGH", "", purpose = "access", method = "nis")
            assertTrue(request.withoutCardPin)
            val challenge = flow.acceptNis(request)
            assertEquals(16, challenge.size)
            val card = NisCardData("123456789012".toByteArray(), byteArrayOf(0x30, 0x00), ByteArray(256) { 1 })
            val wrong = flow.submitNis(request, card, "000001")
            assertIs<Outcome.PinWrong>(wrong).also { assertEquals(4, it.attemptsLeft) }
            assertIs<Outcome.Signed>(flow.submitNis(request, card, "482913"))  // stessi dati, nessun nuovo appoggio
            assertEquals(listOf("prendi", "cie-senza-pin", "cie-senza-pin"), fake.calls)
            assertEquals(Base64Codec.encode(card.nis), fake.nisBodies.last().getString("nis"))
        }
    }

    @Test
    fun accessRequestsAreRecognised() {
        assertTrue(SignRequest("r", "t", null, "00", "C", "", purpose = "access").isAccess)
        assertTrue(!SignRequest("r", "t", null, "00", "C", "").isAccess)
    }
}
