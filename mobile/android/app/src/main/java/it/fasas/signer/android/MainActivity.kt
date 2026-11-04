package it.fasas.signer.android

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.view.WindowManager
import android.widget.EditText
import it.fasas.signer.CardException
import it.fasas.signer.FasasApi
import it.fasas.signer.NisCardData
import it.fasas.signer.Outcome
import it.fasas.signer.ServerException
import it.fasas.signer.SignRequest
import it.fasas.signer.SigningFlow
import java.io.ByteArrayInputStream
import java.io.IOException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * FASAS Signer per Android – versione di prova: CIE + PIN FASAS provata con una CIE reale; firma con il PIN della
 * carta non ancora collaudata.
 * Flusso: richiesta dal FASAS → conferma (codice di controllo) → PIN di 8 cifre → «avvicina la CIE» →
 * sessione NFC (canale sicuro, certificato, firma) → esito. Il PIN non lascia il telefono.
 * La lettura resta attiva finché non c'è un esito: se la carta si sposta basta riappoggiarla.
 * «Prova la lettura della CIE» controlla telefono, carta e PIN senza contattare il FASAS.
 */
class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()   // azioni (abbinamento, presa in carico, annullamento)
    private val poller = Executors.newSingleThreadExecutor()   // attesa delle richieste: un ciclo che non si ferma
    private val polling = AtomicBoolean(false)
    private val busy = AtomicBoolean(false)
    private val cardBusy = AtomicBoolean(false)
    private val ui = Handler(Looper.getMainLooper())
    private val looks by lazy { Ui(this) }
    private lateinit var screen: HomeScreen
    private val status get() = screen.status
    private var api: FasasApi? = null
    private var nfc: NfcAdapter? = null
    /** Cosa fare quando il telefono rileva una carta (null = lettura spenta). Gira su un thread dell'NFC. */
    private var onCard: ((Tag?) -> Unit)? = null
    private var afterNfcSettings: (() -> Unit)? = null
    private val notFoundHint = Runnable {
        if (onCard != null) status.show(StatusPanel.Kind.WAIT_CARD, "Non rilevo ancora la CIE", null, CARD_TIPS)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)  // niente screenshot né anteprime del PIN
        nfc = NfcAdapter.getDefaultAdapter(this)
        render()
    }

    private val prefs get() = getSharedPreferences("fasas_signer", Context.MODE_PRIVATE)

    /** Versione di prova (build debug): accetta anche un FASAS in rete locale via HTTP, es. il PC dell'ufficio. */
    private val testBuild get() = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0

    private fun render() {
        val server = prefs.getString("server", null)
        val token = prefs.getString("token", null)
        val paired = if (server != null && token != null) Paired(server, prefs.getString("user", null)) else null
        api = paired?.let { runCatching { FasasApi(server!!, token!!, allowLanHttp = testBuild) }.getOrNull() }
        screen = HomeScreen(looks, paired, testBuild, nfc?.isEnabled).apply {
            onPair = { address, code -> pair(address, code) }
            onTestCard = { testCard() }
            onPinHelp = { pinHelp() }
            onUnpair = { unpair() }
        }
        showIdle()
        setContentView(screen.root)
    }

    /** Stato di riposo: abbinamento da fare oppure in attesa di richieste dal FASAS. */
    private fun showIdle() {
        val adapter = nfc
        when {
            adapter == null -> status.show(StatusPanel.Kind.ERROR, "NFC assente",
                "Questo telefono non ha l'NFC: non può leggere la CIE.")
            api == null -> status.show(StatusPanel.Kind.SETUP, "Abbina il telefono al FASAS",
                "Serve una volta sola: poi le richieste di firma e di verifica compaiono qui da sole.")
            !adapter.isEnabled -> status.show(StatusPanel.Kind.WARNING, "NFC spento",
                "Attiva l'NFC nelle impostazioni del telefono: serve per leggere la CIE.")
            else -> status.show(StatusPanel.Kind.IDLE, "Pronto", WAITING)
        }
    }

    private fun unpair() {
        AlertDialog.Builder(this).setTitle("Scollegare questo telefono?")
            .setMessage("Il telefono non riceverà più richieste dal FASAS. Per usarlo di nuovo andrà abbinato con un " +
                "nuovo codice. La registrazione della CIE resta valida. Per revocarlo anche dal FASAS: " +
                "Impostazioni › Firma digitale › Revoca.")
            .setPositiveButton("Scollega") { _, _ ->
                polling.set(false)
                prefs.edit().remove("token").remove("server").remove("user").apply()
                render()
            }
            .setNegativeButton("Annulla", null)
            .show()
    }

    private fun pair(server: String, code: String) = worker.execute {
        try {
            val client = FasasApi(server, allowLanHttp = testBuild)
            val data = client.pair(code.trim(), android.os.Build.MODEL ?: "Telefono")
            prefs.edit().putString("server", server.trim()).putString("token", client.token)
                .putString("user", data.optString("user")).apply()
            runOnUiThread {
                render()
                startPolling()
                result(true, "Telefono abbinato", "Collegato al FASAS come ${data.getString("user")}.")
            }
        } catch (e: Exception) {
            runOnUiThread { result(false, "Abbinamento non riuscito", e.message ?: "Controlla indirizzo e codice.") }
        }
    }

    override fun onResume() {
        super.onResume()
        val adapter = nfc
        if (adapter == null) {
            showIdle()
            return
        }
        if (onCard == null && status.kind in setOf(StatusPanel.Kind.IDLE, StatusPanel.Kind.WARNING, StatusPanel.Kind.SETUP)) {
            render()  // NFC acceso o spento nel frattempo: si aggiorna anche la scheda del telefono
        }
        if (adapter.isEnabled) {
            afterNfcSettings?.let { afterNfcSettings = null; it() }
            if (onCard != null) enableReader()  // lettura in corso prima di uscire dall'app: riprende
        } else if (afterNfcSettings == null) {
            AlertDialog.Builder(this).setMessage("L'NFC del telefono è spento: serve per leggere la CIE.")
                .setPositiveButton("Attiva l'NFC") { _, _ -> startActivity(Intent(Settings.ACTION_NFC_SETTINGS)) }
                .setNegativeButton("Non ora", null)
                .show()
        }
        startPolling()
    }

    override fun onPause() {
        polling.set(false)
        ui.removeCallbacks(notFoundHint)
        runCatching { nfc?.disableReaderMode(this) }  // la richiesta resta: si riprende al ritorno nell'app
        super.onPause()
    }

    // --- Lettura della carta ------------------------------------------------------------------------------

    /** Accende la lettura NFC finché non si chiama stopListening: ogni carta rilevata passa a [handler] (null = annullato). */
    private fun listen(title: String, message: String, handler: (Tag?) -> Unit) {
        val adapter = nfc ?: return result(false, "NFC assente", "Questo telefono non ha l'NFC: non può leggere la CIE.")
        if (!adapter.isEnabled) {
            AlertDialog.Builder(this).setMessage("L'NFC del telefono è spento: attivalo per leggere la CIE.")
                .setPositiveButton("Attiva l'NFC") { _, _ ->
                    afterNfcSettings = { listen(title, message, handler) }
                    startActivity(Intent(Settings.ACTION_NFC_SETTINGS))
                }
                .setNegativeButton("Annulla") { _, _ -> handler.invoke(null) }
                .show()
            return
        }
        onCard = handler
        cardBusy.set(false)
        status.show(StatusPanel.Kind.WAIT_CARD, title, message, CARD_TIPS)
        enableReader()
    }

    private fun enableReader() {
        // Senza FLAG_READER_NO_PLATFORM_SOUNDS: il «bip» del telefono conferma che la carta è stata rilevata
        val flags = NfcAdapter.FLAG_READER_NFC_A or NfcAdapter.FLAG_READER_NFC_B or NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK
        nfc?.enableReaderMode(this, { tag -> cardFound(tag) }, flags, null)
        ui.removeCallbacks(notFoundHint)
        ui.postDelayed(notFoundHint, 20_000)
    }

    private fun stopListening() {
        onCard = null
        ui.removeCallbacks(notFoundHint)
        runCatching { nfc?.disableReaderMode(this) }
    }

    /** Thread dell'NFC: una carta alla volta; ogni errore diventa un messaggio (mai un'eccezione persa). */
    private fun cardFound(tag: Tag) {
        val handler = onCard ?: return
        if (!cardBusy.compareAndSet(false, true)) return
        ui.removeCallbacks(notFoundHint)
        vibrate()
        runOnUiThread { status.show(StatusPanel.Kind.READING, "CIE rilevata", "Tienila ferma, non spostarla…") }
        try {
            handler(tag)
        } catch (e: Throwable) {
            runOnUiThread {
                stopListening()
                finish(false, "Lettura non riuscita", "Errore imprevisto (${e.javaClass.simpleName}). Riprova.")
            }
        }
    }

    /** Collega la carta: CardException con un messaggio chiaro se non è una CIE o se il telefono non è adatto. */
    private fun connect(tag: Tag, requireExtended: Boolean = true): IsoDep {
        val isoDep = IsoDep.get(tag) ?: throw CardException("not_cie", IasCieSession.NOT_CIE)
        try {
            isoDep.connect()
        } catch (e: IOException) {
            throw CardException("card_removed", IasCieSession.MOVED)
        }
        isoDep.timeout = 10_000
        if (requireExtended && !isoDep.isExtendedLengthApduSupported) {
            runCatching { isoDep.close() }
            throw CardException("nfc_unsupported", "Questo telefono non supporta i comandi NFC lunghi (extended APDU) " +
                "che servono alla CIE: usare un altro telefono o il lettore del computer.")
        }
        return isoDep
    }

    private fun progress(message: String) = runOnUiThread { status.detail(message) }

    /** La carta si è spostata: si resta in ascolto, basta riappoggiarla. */
    private fun cardMoved(message: String?) {
        status.show(StatusPanel.Kind.WAIT_CARD, "Riappoggia la carta",
            (message ?: IasCieSession.MOVED) + " Tienila ferma finché non compare l'esito.", CARD_TIPS)
        cardBusy.set(false)
    }

    private fun vibrate() = runCatching {
        getSystemService(Vibrator::class.java)?.vibrate(VibrationEffect.createOneShot(80, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    // --- Richieste dal FASAS ------------------------------------------------------------------------------

    private fun startPolling() {
        val client = api ?: return
        if (!polling.compareAndSet(false, true)) return
        poller.execute {
            runCatching {
                client.reportStatus(mapOf("middleware_found" to true, "middleware" to "IAS su NFC (prototipo)",
                    "readers" to listOf("NFC del telefono"), "nfc" to if (nfc?.isEnabled == true) "attivo" else "spento"))
            }
            while (polling.get()) {
                if (busy.get()) { Thread.sleep(1000); continue }
                try {
                    val request = client.pending(wait = 10).firstOrNull() ?: continue
                    busy.set(true)
                    runOnUiThread { confirm(client, request) }
                } catch (e: ServerException) {
                    if (e.status == 401) {
                        prefs.edit().remove("token").apply()
                        runOnUiThread {
                            render()
                            result(false, "Telefono non più abbinato", "Il FASAS ha revocato questo telefono: abbinalo di nuovo.")
                        }
                        polling.set(false)
                    } else {
                        Thread.sleep(5000)
                    }
                }
            }
        }
    }

    private fun dialog() = AlertDialog.Builder(this)

    private fun confirm(client: FasasApi, request: SignRequest) {
        val flow = SigningFlow(client)
        if (request.withoutCardPin) return confirmWithoutCardPin(flow, request)
        val version = request.version?.let { " – versione $it" } ?: ""
        val view = if (request.isAccess) {
            Dialogs.request(looks, "Verifica di identità con CIE", "Per aprire: ${request.title}", request.verifyCode,
                "Conferma solo se il codice coincide con quello mostrato nella pagina del FASAS. Ti verrà chiesto il PIN della carta.")
        } else {
            Dialogs.request(looks, "Richiesta di firma con CIE", "${request.title}$version", request.verifyCode,
                "Firma solo se il codice coincide con quello mostrato nella pagina del FASAS. Ti verrà chiesto il PIN della carta.")
        }
        dialog().setView(view).setCancelable(false)
            .setPositiveButton(if (request.isAccess) "Continua" else "Firma con CIE") { _, _ ->
                worker.execute {
                    try {
                        flow.accept(request)
                        runOnUiThread { askPin(flow, request, null) }
                    } catch (e: ServerException) {
                        runOnUiThread { finish(false, "Richiesta non più valida", e.message ?: "Riprova dal FASAS.") }
                    }
                }
            }
            .setNegativeButton("Rifiuta") { _, _ -> worker.execute { runCatching { flow.refuse(request) }; busy.set(false) } }
            .show()
    }

    // --- CIE senza il suo PIN: registrazione della carta e apertura dei documenti con il PIN FASAS ------------

    private fun confirmWithoutCardPin(flow: SigningFlow, request: SignRequest) {
        val view = if (request.isEnroll) {
            Dialogs.request(looks, "Registrazione della CIE", "Registra la tua CIE per aprire i documenti con il PIN FASAS",
                request.verifyCode, "Non serve il PIN della carta. Conferma solo se il codice coincide con quello " +
                    "mostrato nella pagina del FASAS.")
        } else {
            Dialogs.request(looks, "Verifica di identità", "Per aprire: ${request.title}", request.verifyCode,
                "Conferma solo se il codice coincide con quello mostrato nella pagina del FASAS. Ti verrà chiesto il PIN FASAS.")
        }
        dialog().setView(view).setCancelable(false)
            .setPositiveButton(if (request.isEnroll) "Registra" else "Continua") { _, _ ->
                worker.execute {
                    val challenge = try {
                        flow.acceptNis(request)
                    } catch (e: ServerException) {
                        runOnUiThread { finish(false, "Richiesta non più valida", e.message ?: "Riprova dal FASAS.") }
                        return@execute
                    }
                    runOnUiThread {
                        if (request.isEnroll) readCardWithoutPin(flow, request, challenge, null)
                        else askFasasPin(flow, request, challenge, null, null)
                    }
                }
            }
            .setNegativeButton("Rifiuta") { _, _ -> worker.execute { runCatching { flow.refuse(request) }; busy.set(false) } }
            .show()
    }

    /** PIN FASAS (scelto al primo accesso). Dopo un PIN errato si reinviano i dati già letti: niente nuovo appoggio. */
    private fun askFasasPin(flow: SigningFlow, request: SignRequest, challenge: ByteArray, error: String?, card: NisCardData?) {
        val (view, field) = Dialogs.pin(looks, error, "Il PIN che hai scelto nel FASAS al primo accesso: non è il PIN " +
            "della carta né quello del telefono.", 8, "6-8 cifre")
        dialog().setTitle("PIN FASAS").setView(view).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                when {
                    pin.length < 6 -> askFasasPin(flow, request, challenge, "Il PIN FASAS ha da 6 a 8 cifre.", card)
                    card != null -> {
                        status.show(StatusPanel.Kind.READING, "Controllo in corso", "Il FASAS controlla il PIN FASAS…")
                        worker.execute { handleNisOutcome(flow, request, challenge, card, flow.submitNis(request, card, pin)) }
                    }
                    else -> readCardWithoutPin(flow, request, challenge, pin)
                }
            }
            .setNegativeButton("Annulla") { _, _ -> worker.execute { flow.cancel(request); busy.set(false) } }
            .show()
            .also { focus(field) }
    }

    private fun readCardWithoutPin(flow: SigningFlow, request: SignRequest, challenge: ByteArray, pin: String?) {
        listen("Avvicina la CIE", "Appoggia la carta al retro del telefono e tienila ferma fino alla fine. " +
            "Non serve il suo PIN.") { tag ->
            if (tag == null) {
                worker.execute { flow.cancel(request); busy.set(false) }
                runOnUiThread { showIdle() }
                return@listen
            }
            val card = try {
                val isoDep = connect(tag, requireExtended = false)
                try {
                    NisSession(isoDep, ::progress).read(challenge, withSod = request.isEnroll)
                } finally {
                    runCatching { isoDep.close() }
                }
            } catch (e: CardException) {
                if (e.code == "card_removed") {
                    runOnUiThread { cardMoved(e.message) }
                    return@listen
                }
                flow.abort(request, e.code)
                runOnUiThread { stopListening(); finish(false, "Lettura non riuscita", e.message ?: e.code) }
                return@listen
            }
            runOnUiThread {
                stopListening()
                status.show(StatusPanel.Kind.READING, "Carta letta", "Il FASAS controlla la carta…")
            }
            handleNisOutcome(flow, request, challenge, card, flow.submitNis(request, card, pin))
        }
    }

    private fun handleNisOutcome(flow: SigningFlow, request: SignRequest, challenge: ByteArray, card: NisCardData,
                                 outcome: Outcome) = runOnUiThread {
        when (outcome) {
            is Outcome.Signed -> if (request.isEnroll) {
                finish(true, "CIE registrata", "Ora nel FASAS scegli il PIN FASAS (Impostazioni › Firma digitale); poi " +
                    "l'amministratore conferma la registrazione vedendo la carta.")
            } else {
                finish(true, "Identità verificata", "Torna al FASAS: il documento si apre.")
            }
            is Outcome.PinWrong -> askFasasPin(flow, request, challenge,
                "PIN FASAS errato." + (outcome.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""), card)
            is Outcome.Failed -> finish(false, if (request.isEnroll) "Registrazione non riuscita" else "Verifica non riuscita",
                outcome.message)
            is Outcome.CardMoved -> finish(false, "Lettura interrotta", outcome.message)
        }
    }

    private fun askPin(flow: SigningFlow, request: SignRequest, error: String?) {
        val (view, field) = Dialogs.pin(looks, error, "PIN della carta, 8 cifre: non è il PIN FASAS. Va solo alla carta, " +
            "non al FASAS. Se non lo ricordi premi Annulla e non tirare a indovinare: 3 PIN errati bloccano la carta " +
            "(si sblocca con il PUK nell'app CieID).", 8, "8 cifre")
        dialog().setTitle("PIN della CIE").setView(view).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                if (pin.length != 8) askPin(flow, request, "Il PIN della carta ha 8 cifre.") else readForRequest(flow, request, pin)
            }
            .setNeutralButton("Dove lo trovo?") { _, _ -> pinHelp { askPin(flow, request, error) } }
            .setNegativeButton("Annulla") { _, _ -> worker.execute { flow.cancel(request); busy.set(false) } }
            .show()
            .also { focus(field) }
    }

    private fun readForRequest(flow: SigningFlow, request: SignRequest, pin: String) {
        listen("Avvicina la CIE", "Appoggia la carta al retro del telefono e tienila ferma fino alla fine (alcuni secondi).") { tag ->
            if (tag == null) {
                worker.execute { flow.cancel(request); busy.set(false) }
                runOnUiThread { showIdle() }
                return@listen
            }
            val outcome = try {
                val isoDep = connect(tag)
                try {
                    flow.onCard(request, IasCieSession(isoDep, ::progress), pin)
                } finally {
                    runCatching { isoDep.close() }
                }
            } catch (e: CardException) {
                if (e.code == "card_removed") Outcome.CardMoved(e.message ?: IasCieSession.MOVED)
                else Outcome.Failed(e.code, e.message ?: e.code).also { flow.abort(request, e.code) }
            } catch (e: Exception) {
                Outcome.Failed("device_error", "errore imprevisto (${e.javaClass.simpleName}).")
                    .also { flow.abort(request, "device_error") }
            }
            runOnUiThread {
                when (outcome) {
                    is Outcome.CardMoved -> cardMoved(outcome.message)
                    is Outcome.PinWrong -> {
                        stopListening()
                        askPin(flow, request, "PIN errato." + (outcome.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""))
                    }
                    is Outcome.Signed -> {
                        stopListening()
                        if (request.isAccess) finish(true, "Identità verificata", "Torna al FASAS: il documento si apre.")
                        else finish(true, "Documento firmato", "Firma elettronica avanzata con CIE (${outcome.level}).")
                    }
                    is Outcome.Failed -> {
                        stopListening()
                        finish(false, if (request.isAccess) "Verifica non riuscita" else "Firma non riuscita", outcome.message)
                    }
                }
            }
        }
    }

    // --- Prova della carta (nessun contatto con il FASAS) ---------------------------------------------------

    private fun testCard() {
        if (onCard != null) return result(false, "Lettura già in corso", "Termina prima la lettura in corso.")
        listen("Prova della CIE", "Appoggia la carta al retro del telefono e tienila ferma. Non serve il PIN e " +
            "non si contatta il FASAS.") { tag ->
            if (tag == null) return@listen runOnUiThread { showIdle() }
            val error = try {
                val isoDep = connect(tag)
                try { IasCieSession(isoDep).check() } finally { runCatching { isoDep.close() } }
                null
            } catch (e: CardException) {
                e
            }
            runOnUiThread {
                if (error?.code == "card_removed") return@runOnUiThread cardMoved(error.message)
                stopListening()
                showIdle()
                if (error != null) return@runOnUiThread result(false, "Lettura non riuscita", error.message ?: error.code)
                dialog().setView(Dialogs.result(looks, true, "CIE letta correttamente",
                    "Il telefono legge la carta. Puoi provare anche il PIN della carta: la carta lo controlla e mostra il " +
                        "tuo codice fiscale. Nessun dato viene inviato al FASAS. Attenzione: 3 PIN errati bloccano la carta."))
                    .setPositiveButton("Prova il PIN") { _, _ -> testPin(null) }
                    .setNegativeButton("Chiudi", null)
                    .show()
            }
        }
    }

    private fun testPin(error: String?) {
        val (view, field) = Dialogs.pin(looks, error, "PIN della carta, 8 cifre. Se non lo ricordi premi Annulla.", 8, "8 cifre")
        dialog().setTitle("Prova del PIN della CIE").setView(view).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                if (pin.length != 8) testPin("Il PIN della carta ha 8 cifre.") else testPinWithCard(pin)
            }
            .setNeutralButton("Dove lo trovo?") { _, _ -> pinHelp { testPin(error) } }
            .setNegativeButton("Annulla", null)
            .show()
            .also { focus(field) }
    }

    private fun testPinWithCard(pin: String) {
        listen("Avvicina di nuovo la CIE", "Tienila ferma alcuni secondi: la carta controlla il PIN.") { tag ->
            if (tag == null) return@listen runOnUiThread { showIdle() }
            val outcome: Pair<Boolean, String> = try {
                val isoDep = connect(tag)
                val der = try {
                    IasCieSession(isoDep, ::progress).run { open(pin); readCertificate() }
                } finally {
                    runCatching { isoDep.close() }
                }
                true to describeCertificate(der)
            } catch (e: CardException) {
                if (e.code == "card_removed") {
                    runOnUiThread { cardMoved(e.message) }
                    return@listen
                }
                if (e.code == "pin_wrong") {
                    return@listen runOnUiThread {
                        stopListening()
                        showIdle()
                        testPin("PIN errato." + (e.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""))
                    }
                }
                false to (e.message ?: e.code)
            }
            runOnUiThread {
                stopListening()
                showIdle()
                result(outcome.first, if (outcome.first) "PIN corretto" else "Prova non riuscita", outcome.second)
            }
        }
    }

    private fun describeCertificate(der: ByteArray): String {
        val cert = CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(der)) as X509Certificate
        val subject = cert.subjectX500Principal.name.uppercase()
        val fiscalCode = FISCAL_CODE.find(subject)?.value
        val until = SimpleDateFormat("dd/MM/yyyy", Locale.ITALY).format(cert.notAfter)
        return "La CIE funziona con questo telefono.\n\n" +
            (fiscalCode?.let { "Codice fiscale sulla carta: $it\n" } ?: "") +
            "Certificato valido fino al $until\n\n" +
            "Il codice fiscale deve essere uguale a quello del tuo profilo nel FASAS. Nessun dato è stato inviato."
    }

    private fun pinHelp(then: (() -> Unit)? = null) {
        dialog().setTitle("PIN della CIE").setView(Dialogs.help(looks, listOf(
            "Non lo scegli tu: è il PIN di 8 cifre della tua Carta d'Identità Elettronica.",
            "• Le prime 4 cifre sono sulla ricevuta che ti hanno dato in Comune quando hai chiesto la carta.\n" +
                "• Le ultime 4 cifre sono nella lettera arrivata insieme alla CIE.",
            "Scrivile una dopo l'altra, prima le 4 della ricevuta. Se l'hai cambiato con l'app «CieID», usa quello nuovo.",
            "Non è il PIN del telefono, né il PIN FASAS, né la password del FASAS. Dopo 3 tentativi errati la carta si " +
                "blocca: si sblocca con il PUK nell'app «CieID». Se hai perso il PIN, il Comune lo ristampa.",
        )))
            .setPositiveButton("Ho capito") { _, _ -> then?.invoke() }
            .show()
    }

    /** Fine di un'operazione: si torna allo stato di riposo e si mostra l'esito. */
    private fun finish(ok: Boolean, title: String, message: String) {
        showIdle()
        busy.set(false)
        result(ok, title, message)
    }

    private fun result(ok: Boolean, title: String, message: String) {
        dialog().setView(Dialogs.result(looks, ok, title, message)).setPositiveButton("OK", null).show()
    }

    /** Tastiera numerica aperta subito sul campo del PIN. */
    private fun focus(field: EditText) {
        field.requestFocus()
        field.postDelayed({
            getSystemService(android.view.inputmethod.InputMethodManager::class.java)
                ?.showSoftInput(field, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
        }, 150)
    }

    companion object {
        private const val WAITING = "In attesa di richieste dal FASAS. Quando dal FASAS avvii una firma o una " +
            "verifica, la richiesta compare qui."
        private const val CARD_TIPS = "Togli la cover. Appoggia la carta al centro del retro, vicino alla fotocamera, " +
            "e spostala lentamente finché il telefono vibra; poi non muoverla."
        private val FISCAL_CODE = Regex("[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")
    }
}
