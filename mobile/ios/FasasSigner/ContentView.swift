// FASAS Signer per iPhone – PROTOTIPO: compilato nella CI, non collaudato con una CIE reale.
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var model: SignerModel
    @State private var server = SignerModel.testBuild ? "http://" : "https://"
    @State private var code = ""
    @State private var pin = ""

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Firma elettronica avanzata con la CIE. Prototipo: non ancora collaudato con una CIE reale.")
                        .font(.footnote).foregroundColor(.secondary)
                    if SignerModel.testBuild {
                        Text("VERSIONE DI PROVA: si collega anche a un FASAS sul PC della stessa rete Wi-Fi.")
                            .font(.footnote).bold().padding(8).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.red).foregroundColor(.white).cornerRadius(6)
                    }
                    content
                    if !model.status.isEmpty {
                        Text(model.status).font(.footnote).foregroundColor(.secondary)
                    }
                }
                .padding()
            }
            .navigationTitle("FASAS Signer")
        }
        .navigationViewStyle(.stack)
    }

    @ViewBuilder private var content: some View {
        switch model.phase {
        case .unpaired:
            Text("Nel FASAS apri Impostazioni › Firma digitale › «Abbina un nuovo FASAS Signer».")
            TextField("Indirizzo del FASAS", text: $server)
                .keyboardType(.URL).textInputAutocapitalization(.never).disableAutocorrection(true)
                .textFieldStyle(.roundedBorder)
            TextField("Codice di abbinamento", text: $code)
                .textInputAutocapitalization(.characters).disableAutocorrection(true).textFieldStyle(.roundedBorder)
            Button("Abbina") { Task { await model.pair(server: server, code: code) } }
                .buttonStyle(.borderedProminent)
        case .idle:
            Text(model.user.isEmpty ? "In attesa di richieste di firma dal FASAS…"
                 : "In linea come \(model.user): in attesa di richieste di firma dal FASAS…")
            ProgressView()
        case .confirm(let request):
            Text("Richiesta di firma con CIE").font(.headline)
            Text(request.title + (request.version.map { " – versione \($0)" } ?? ""))
            Text("Codice di controllo").font(.caption).foregroundColor(.secondary)
            Text(request.verify_code).font(.system(size: 30, weight: .bold, design: .monospaced))
            Text("Firma solo se il codice coincide con quello mostrato nella pagina del FASAS.").font(.footnote)
            HStack {
                Button("Firma con CIE") { Task { await model.accept(request) } }.buttonStyle(.borderedProminent)
                Button("Rifiuta", role: .cancel) { Task { await model.refuse(request) } }.buttonStyle(.bordered)
            }
        case .pin(let request, let message):
            Text("PIN della CIE").font(.headline)
            Text("Codice di controllo: \(request.verify_code)").font(.subheadline.monospaced())
            if let message { Text(message).foregroundColor(.red) }
            Text("Digita il PIN completo della CIE (8 cifre): va solo alla carta.").font(.footnote)
            SecureField("8 cifre", text: $pin).keyboardType(.numberPad).textFieldStyle(.roundedBorder)
            HStack {
                Button("Avanti") {
                    let value = pin
                    pin = ""
                    Task { await model.sign(request, pin: value) }
                }
                .buttonStyle(.borderedProminent).disabled(pin.count != 8 || !pin.allSatisfy(\.isNumber))
                Button("Annulla", role: .cancel) {
                    pin = ""
                    Task { await model.cancel(request) }
                }
                .buttonStyle(.bordered)
            }
        case .signing:
            ProgressView("Avvicina la CIE al retro dell'iPhone e tienila ferma…")
        case .result(let text):
            Text(text)
            Button("OK") { model.dismissResult() }.buttonStyle(.borderedProminent)
        }
    }
}
