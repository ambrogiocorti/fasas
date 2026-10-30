// FASAS Signer per iPhone – PROTOTIPO: compilato nella CI, non collaudato con una CIE reale.
import Foundation
import UIKit

@MainActor
final class SignerModel: ObservableObject {
    enum Phase: Equatable {
        case unpaired
        case idle
        case confirm(SignRequest)
        case pin(SignRequest, String?)
        case signing(SignRequest)
        case result(String)
    }

    /// Versione di prova (build Debug): accetta anche un FASAS sul PC della stessa Wi-Fi (http://192.168…).
    static var testBuild: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }

    @Published var phase: Phase = .unpaired
    @Published var status = ""
    @Published var user = ""
    private var api: FasasAPI?
    private var signer: CieSigner?
    private var pollTask: Task<Void, Never>?

    init() {
        if let server = UserDefaults.standard.string(forKey: "server"), let token = Keychain.read("token"),
           let api = try? FasasAPI(server: server, token: token, allowLanHttp: SignerModel.testBuild) {
            self.api = api
            phase = .idle
            startPolling()
        }
    }

    func pair(server: String, code: String) async {
        do {
            let api = try FasasAPI(server: server, allowLanHttp: SignerModel.testBuild)
            user = try await api.pair(code: code.trimmingCharacters(in: .whitespaces),
                                      name: UIDevice.current.name)
            Keychain.save(api.token, for: "token")
            UserDefaults.standard.set(server.trimmingCharacters(in: .whitespaces), forKey: "server")
            self.api = api
            phase = .idle
            status = "Abbinato all'utente \(user)."
            startPolling()
        } catch {
            status = error.localizedDescription
        }
    }

    func unpair() {
        pollTask?.cancel()
        Keychain.delete("token")
        api = nil
        phase = .unpaired
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in await self?.poll() }
    }

    private func poll() async {
        guard let api else { return }
        try? await api.reportStatus([
            "middleware_found": CieSigner.nfcAvailable, "middleware": "CieSDK su Core NFC (prototipo)",
            "readers": ["NFC dell'iPhone"], "nfc": CieSigner.nfcAvailable ? "disponibile" : "non disponibile",
        ])
        if let name = try? await api.me() { user = name }
        while !Task.isCancelled {
            guard phase == .idle else {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                continue
            }
            do {
                if let request = try await api.pending(wait: 10).first, phase == .idle {
                    phase = .confirm(request)
                }
            } catch let error as ServerError where error.status == 401 {
                status = "Dispositivo revocato o non abbinato: abbinalo di nuovo dal FASAS."
                unpair()
                return
            } catch {
                status = error.localizedDescription
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    func accept(_ request: SignRequest) async {
        guard let api else { return }
        let signer = CieSigner(api: api)
        self.signer = signer
        do {
            try await signer.accept(request)
            phase = .pin(request, nil)
        } catch {
            phase = .result("Firma non riuscita: \(error.localizedDescription)")
        }
    }

    func refuse(_ request: SignRequest) async {
        if let api { await CieSigner(api: api).refuse(request) }
        phase = .idle
    }

    func cancel(_ request: SignRequest) async {
        await signer?.cancel(request)
        phase = .idle
    }

    func sign(_ request: SignRequest, pin: String) async {
        guard let signer else { return }
        phase = .signing(request)
        switch await signer.sign(request, pin: pin) {
        case .signed(let level):
            phase = .result("Documento firmato correttamente (\(level)).")
        case .pinWrong(let left):
            let rest = left.map { " Tentativi rimasti: \($0)." } ?? ""
            phase = .pin(request, "PIN errato.\(rest) Dopo 3 errori il PIN si blocca.")
        case .failed(_, let message):
            phase = .result("Firma non riuscita: \(message)")
        }
    }

    func dismissResult() {
        phase = .idle
    }
}
