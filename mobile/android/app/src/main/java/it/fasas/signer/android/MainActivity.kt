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
import android.text.InputFilter
import android.text.InputType
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
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
 * FASAS Signer per Android – PROTOTIPO NON ANCORA COLLAUDATO con una CIE reale.
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
    private lateinit var status: TextView
    private var api: FasasApi? = null
    private var nfc: NfcAdapter? = null
    /** Cosa fare quando il telefono rileva una carta (null = lettura spenta). Gira su un thread dell'NFC. */
    private var onCard: ((Tag?) -> Unit)? = null
    private var afterNfcSettings: (() -> Unit)? = null
    private val notFoundHint = Runnable {
        if (onCard != null) status.text = "Non rilevo ancora la CIE.\n\n$CARD_TIPS"
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
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(48, 64, 48, 48) }
        root.addView(TextView(this).apply { text = "FASAS Signer – CIE"; textSize = 22f })
        root.addView(TextView(this).apply {
            text = "Firma elettronica avanzata e verifica di identità con la Carta d'Identità Elettronica. " +
                "Prototipo: non ancora collaudato con una CIE reale."
            setPadding(0, 8, 0, 24)
        })
        if (testBuild) {
            root.addView(TextView(this).apply {
                text = "App di prova: si collega anche al FASAS sul PC della stessa Wi-Fi (http://192.168…). " +
                    "La CIE e il PIN sono quelli veri."
                setBackgroundColor(0xFFB00020.toInt())
                setTextColor(0xFFFFFFFF.toInt())
                setPadding(24, 16, 24, 16)
            })
        }
        status = TextView(this).apply { textSize = 16f; setPadding(0, 24, 0, 24) }
        root.addView(status)
        val server = prefs.getString("server", null)
        val token = prefs.getString("token", null)
        if (server == null || token == null) {
            val serverField = EditText(this).apply {
                hint = if (testBuild) "Indirizzo del FASAS (es. http://192.168.1.20:8000/)" else "Indirizzo del FASAS (https://…)"
                setText(if (testBuild) "http://" else "https://")
            }
            val codeField = EditText(this).apply { hint = "Codice di abbinamento" }
            root.addView(serverField)
            root.addView(codeField)
            root.addView(Button(this).apply {
                text = "Abbina"
                setOnClickListener { pair(serverField.text.toString(), codeField.text.toString()) }
            })
            status.text = "Nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer»."
        } else {
            api = runCatching { FasasApi(server, token, allowLanHttp = testBuild) }.getOrNull()
            status.text = WAITING
        }
        root.addView(Button(this).apply { text = "Prova la lettura della CIE"; setOnClickListener { testCard() } })
        root.addView(Button(this).apply { text = "Dove trovo il PIN della CIE?"; setOnClickListener { pinHelp() } })
        setContentView(root)
    }

    private fun pair(server: String, code: String) = worker.execute {
        try {
            val client = FasasApi(server, allowLanHttp = testBuild)
            val data = client.pair(code.trim(), android.os.Build.MODEL ?: "Telefono")
            prefs.edit().putString("server", server.trim()).putString("token", client.token).apply()
            runOnUiThread { render(); show("Abbinato all'utente ${data.getString("user")}.") }
        } catch (e: Exception) {
            runOnUiThread { show(e.message ?: "Abbinamento non riuscito.") }
        }
    }

    override fun onResume() {
        super.onResume()
        val adapter = nfc
        if (adapter == null) {
            status.text = "Questo telefono non ha l'NFC: non può leggere la CIE."
            return
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
    private fun listen(message: String, handler: (Tag?) -> Unit) {
        val adapter = nfc ?: return show("Questo telefono non ha l'NFC: non può leggere la CIE.")
        if (!adapter.isEnabled) {
            AlertDialog.Builder(this).setMessage("L'NFC del telefono è spento: attivalo per leggere la CIE.")
                .setPositiveButton("Attiva l'NFC") { _, _ ->
                    afterNfcSettings = { listen(message, handler) }
                    startActivity(Intent(Settings.ACTION_NFC_SETTINGS))
                }
                .setNegativeButton("Annulla") { _, _ -> handler.invoke(null) }
                .show()
            return
        }
        onCard = handler
        cardBusy.set(false)
        status.text = message
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
        runOnUiThread { status.text = "CIE rilevata: tienila ferma, non spostarla…" }
        try {
            handler(tag)
        } catch (e: Throwable) {
            runOnUiThread {
                stopListening()
                finish("Errore imprevisto durante la lettura (${e.javaClass.simpleName}). Riprova.")
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

    private fun progress(message: String) = runOnUiThread { status.text = message }

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
                        runOnUiThread { render(); show("Dispositivo revocato o non abbinato: abbinalo di nuovo.") }
                        polling.set(false)
                    } else {
                        Thread.sleep(5000)
                    }
                }
            }
        }
    }

    private fun confirm(client: FasasApi, request: SignRequest) {
        val flow = SigningFlow(client)
        if (request.withoutCardPin) return confirmWithoutCardPin(flow, request)
        val version = request.version?.let { " – versione $it" } ?: ""
        val builder = AlertDialog.Builder(this).setCancelable(false)
        if (request.isAccess) {
            builder.setTitle("Verifica di identità con CIE")
                .setMessage("Per aprire: ${request.title}\n\nCodice di controllo:\n${request.verifyCode}\n\n" +
                    "Conferma solo se il codice coincide con quello mostrato nella pagina del FASAS.")
        } else {
            builder.setTitle("Richiesta di firma con CIE")
                .setMessage("${request.title}$version\n\nCodice di controllo:\n${request.verifyCode}\n\n" +
                    "Firma solo se il codice coincide con quello mostrato nella pagina del FASAS.")
        }
        builder.setPositiveButton(if (request.isAccess) "Verifica con CIE" else "Firma con CIE") { _, _ ->
            worker.execute {
                try {
                    flow.accept(request)
                    runOnUiThread { askPin(flow, request, null) }
                } catch (e: ServerException) {
                    runOnUiThread { finish(e.message ?: "Errore") }
                }
            }
        }
            .setNegativeButton("Rifiuta") { _, _ -> worker.execute { runCatching { flow.refuse(request) }; busy.set(false) } }
            .show()
    }

    // --- CIE senza il suo PIN: registrazione della carta e apertura dei documenti con il PIN FASAS ------------

    private fun confirmWithoutCardPin(flow: SigningFlow, request: SignRequest) {
        val builder = AlertDialog.Builder(this).setCancelable(false)
        if (request.isEnroll) {
            builder.setTitle("Registrazione della CIE")
                .setMessage("Registra la tua CIE per aprire i documenti con il PIN FASAS.\n\nCodice di controllo:\n" +
                    "${request.verifyCode}\n\nNon serve il PIN della carta. Conferma solo se il codice coincide con " +
                    "quello mostrato nella pagina del FASAS.")
        } else {
            builder.setTitle("Verifica di identità")
                .setMessage("Per aprire: ${request.title}\n\nCodice di controllo:\n${request.verifyCode}\n\n" +
                    "Conferma solo se il codice coincide con quello mostrato nella pagina del FASAS.")
        }
        builder.setPositiveButton(if (request.isEnroll) "Registra" else "Continua") { _, _ ->
            worker.execute {
                val challenge = try {
                    flow.acceptNis(request)
                } catch (e: ServerException) {
                    runOnUiThread { finish(e.message ?: "Errore") }
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
    private fun askFasasPin(flow: SigningFlow, request: SignRequest, challenge: ByteArray, message: String?, card: NisCardData?) {
        val field = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            filters = arrayOf(InputFilter.LengthFilter(8))
            gravity = Gravity.CENTER
            hint = "6-8 cifre"
        }
        AlertDialog.Builder(this).setTitle("PIN FASAS")
            .setMessage((message?.let { "$it\n\n" } ?: "") + "Il PIN che hai scelto nel FASAS al primo accesso: " +
                "non è il PIN della carta né quello del telefono.")
            .setView(field).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                when {
                    pin.length < 6 -> askFasasPin(flow, request, challenge, "Il PIN FASAS ha da 6 a 8 cifre.", card)
                    card != null -> worker.execute { handleNisOutcome(flow, request, challenge, card, pin, flow.submitNis(request, card, pin)) }
                    else -> readCardWithoutPin(flow, request, challenge, pin)
                }
            }
            .setNegativeButton("Annulla") { _, _ -> worker.execute { flow.cancel(request); busy.set(false) } }
            .show()
    }

    private fun readCardWithoutPin(flow: SigningFlow, request: SignRequest, challenge: ByteArray, pin: String?) {
        listen("Appoggia la CIE al retro del telefono e tienila ferma fino alla fine (non serve il suo PIN).\n\n$CARD_TIPS") { tag ->
            if (tag == null) {
                worker.execute { flow.cancel(request); busy.set(false) }
                runOnUiThread { status.text = idleText() }
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
                    runOnUiThread { status.text = "${e.message}\nRiappoggiala e tienila ferma."; cardBusy.set(false) }
                    return@listen
                }
                flow.abort(request, e.code)
                runOnUiThread { stopListening(); finish("Lettura non riuscita: ${e.message}") }
                return@listen
            }
            runOnUiThread { stopListening(); status.text = "Carta letta: controllo in corso…" }
            handleNisOutcome(flow, request, challenge, card, pin, flow.submitNis(request, card, pin))
        }
    }

    private fun handleNisOutcome(flow: SigningFlow, request: SignRequest, challenge: ByteArray, card: NisCardData,
                                 pin: String?, outcome: Outcome) = runOnUiThread {
        when (outcome) {
            is Outcome.Signed -> finish(if (request.isEnroll)
                "CIE registrata. Ora nel FASAS scegli il PIN FASAS (Impostazioni › Firma digitale); poi l'amministratore " +
                    "conferma la registrazione vedendo la carta."
            else "Identità verificata: torna al FASAS, il documento si apre.")
            is Outcome.PinWrong -> askFasasPin(flow, request, challenge,
                "PIN FASAS errato." + (outcome.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""), card)
            is Outcome.Failed -> finish("Non riuscito: ${outcome.message}")
            is Outcome.CardMoved -> finish(outcome.message)
        }
    }

    private fun pinField() = EditText(this).apply {
        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        filters = arrayOf(InputFilter.LengthFilter(8))
        gravity = Gravity.CENTER
        hint = "8 cifre"
    }

    private fun askPin(flow: SigningFlow, request: SignRequest, message: String?) {
        val field = pinField()
        AlertDialog.Builder(this).setTitle("PIN della CIE")
            .setMessage((message?.let { "$it\n\n" } ?: "") + "PIN completo della CIE, 8 cifre. Va solo alla carta, " +
                "non al FASAS. Attenzione: 3 PIN errati bloccano la carta.")
            .setView(field).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                if (pin.length != 8) askPin(flow, request, "Il PIN deve avere 8 cifre.") else readForRequest(flow, request, pin)
            }
            .setNeutralButton("Dove lo trovo?") { _, _ -> pinHelp { askPin(flow, request, message) } }
            .setNegativeButton("Annulla") { _, _ -> worker.execute { flow.cancel(request); busy.set(false) } }
            .show()
    }

    private fun readForRequest(flow: SigningFlow, request: SignRequest, pin: String) {
        listen("Appoggia la CIE al retro del telefono e tienila ferma fino alla fine (alcuni secondi).\n\n$CARD_TIPS") { tag ->
            if (tag == null) {
                worker.execute { flow.cancel(request); busy.set(false) }
                runOnUiThread { status.text = WAITING }
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
                    is Outcome.CardMoved -> {
                        status.text = "${outcome.message}\nRiappoggiala e tienila ferma finché non compare l'esito."
                        cardBusy.set(false)
                    }
                    is Outcome.PinWrong -> {
                        stopListening()
                        askPin(flow, request, "PIN errato." + (outcome.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""))
                    }
                    is Outcome.Signed -> {
                        stopListening()
                        finish(if (request.isAccess) "Identità verificata: torna al FASAS, il documento si apre."
                               else "Documento firmato correttamente (${outcome.level}).")
                    }
                    is Outcome.Failed -> {
                        stopListening()
                        finish((if (request.isAccess) "Verifica non riuscita: " else "Firma non riuscita: ") + outcome.message)
                    }
                }
            }
        }
    }

    // --- Prova della carta (nessun contatto con il FASAS) ---------------------------------------------------

    private fun testCard() {
        if (onCard != null) return show("C'è già una lettura in corso.")
        listen("Prova: appoggia la CIE al retro del telefono e tienila ferma.\n\n$CARD_TIPS") { tag ->
            if (tag == null) return@listen runOnUiThread { status.text = idleText() }
            val result = try {
                val isoDep = connect(tag)
                try { IasCieSession(isoDep).check() } finally { runCatching { isoDep.close() } }
                null
            } catch (e: CardException) {
                e
            }
            runOnUiThread {
                if (result?.code == "card_removed") {
                    status.text = "${result.message}\nRiappoggiala e tienila ferma."
                    cardBusy.set(false)
                    return@runOnUiThread
                }
                stopListening()
                status.text = idleText()
                if (result != null) return@runOnUiThread show("Lettura non riuscita: ${result.message}")
                AlertDialog.Builder(this).setTitle("CIE letta correttamente")
                    .setMessage("Il telefono legge la carta. Puoi provare anche il PIN: la carta lo controlla e mostra " +
                        "il tuo codice fiscale. Nessun dato viene inviato al FASAS.\n\nAttenzione: 3 PIN errati bloccano la carta.")
                    .setPositiveButton("Prova il PIN") { _, _ -> testPin(null) }
                    .setNegativeButton("Chiudi", null)
                    .show()
            }
        }
    }

    private fun testPin(message: String?) {
        val field = pinField()
        AlertDialog.Builder(this).setTitle("Prova del PIN della CIE")
            .setMessage((message?.let { "$it\n\n" } ?: "") + "PIN completo, 8 cifre.")
            .setView(field).setCancelable(false)
            .setPositiveButton("Avanti") { _, _ ->
                val pin = field.text.toString()
                field.text.clear()
                if (pin.length != 8) testPin("Il PIN deve avere 8 cifre.") else testPinWithCard(pin)
            }
            .setNeutralButton("Dove lo trovo?") { _, _ -> pinHelp { testPin(message) } }
            .setNegativeButton("Annulla", null)
            .show()
    }

    private fun testPinWithCard(pin: String) {
        listen("Appoggia di nuovo la CIE e tienila ferma (alcuni secondi).") { tag ->
            if (tag == null) return@listen runOnUiThread { status.text = idleText() }
            val text = try {
                val isoDep = connect(tag)
                val der = try {
                    IasCieSession(isoDep, ::progress).run { open(pin); readCertificate() }
                } finally {
                    runCatching { isoDep.close() }
                }
                describeCertificate(der)
            } catch (e: CardException) {
                if (e.code == "card_removed") {
                    runOnUiThread { status.text = "${e.message}\nRiappoggiala e tienila ferma."; cardBusy.set(false) }
                    return@listen
                }
                if (e.code == "pin_wrong") {
                    return@listen runOnUiThread {
                        stopListening()
                        status.text = idleText()
                        testPin("PIN errato." + (e.attemptsLeft?.let { " Tentativi rimasti: $it." } ?: ""))
                    }
                }
                "Prova non riuscita: ${e.message}"
            }
            runOnUiThread { stopListening(); status.text = idleText(); show(text) }
        }
    }

    private fun describeCertificate(der: ByteArray): String {
        val cert = CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(der)) as X509Certificate
        val subject = cert.subjectX500Principal.name.uppercase()
        val fiscalCode = FISCAL_CODE.find(subject)?.value
        val until = SimpleDateFormat("dd/MM/yyyy", Locale.ITALY).format(cert.notAfter)
        return "PIN corretto: la CIE funziona con questo telefono.\n\n" +
            (fiscalCode?.let { "Codice fiscale sulla carta: $it\n" } ?: "") +
            "Certificato valido fino al $until\n\n" +
            "Il codice fiscale deve essere uguale a quello del tuo profilo nel FASAS. Nessun dato è stato inviato."
    }

    private fun pinHelp(then: (() -> Unit)? = null) {
        AlertDialog.Builder(this).setTitle("PIN della CIE")
            .setMessage("Non lo scegli tu: è il PIN di 8 cifre della tua Carta d'Identità Elettronica.\n\n" +
                "• le prime 4 cifre sono sulla ricevuta che ti hanno dato in Comune quando hai chiesto la carta;\n" +
                "• le ultime 4 cifre sono nella lettera arrivata insieme alla CIE.\n\n" +
                "Scrivile una dopo l'altra (prima le 4 della ricevuta). Se l'hai cambiato con l'app «CIE ID», usa quello nuovo.\n\n" +
                "Non è il PIN del telefono né la password del FASAS. Dopo 3 tentativi errati la carta si blocca: " +
                "si sblocca con il PUK nell'app «CIE ID». Se hai perso il PIN, il Comune lo ristampa.")
            .setPositiveButton("Ho capito") { _, _ -> then?.invoke() }
            .show()
    }

    private fun idleText() = if (api != null) WAITING else "Nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer»."

    private fun finish(message: String) {
        status.text = idleText()
        busy.set(false)
        show(message)
    }

    private fun show(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("OK", null).show()
    }

    companion object {
        private const val WAITING = "In attesa di richieste dal FASAS…"
        private const val CARD_TIPS = "Consigli: togli la cover; appoggia la carta al centro del retro, vicino alla " +
            "fotocamera, e spostala lentamente finché il telefono vibra; poi non muoverla. L'NFC deve essere attivo."
        private val FISCAL_CODE = Regex("[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")
    }
}
