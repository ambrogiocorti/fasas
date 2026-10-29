// FASAS Signer per iOS – PROTOTIPO NON COMPILATO NÉ COLLAUDATO.
// Richiede CieSDK (pagopa/cie-sdk-ios, MIT) con la patch patches/cie-sdk-ios-63d2195-performSignature.patch.
import CieSDK
import CryptoKit
import Foundation

enum SignOutcome { case signed(level: String), pinWrong(attemptsLeft: Int?), failed(code: String, message: String) }

/// Flusso: conferma → PIN (8 cifre) → una sessione Core NFC: canale sicuro, certificato, preparazione sul
/// server, firma del DigestInfo. Il PIN resta sul telefono; nessun dato della carta nei log (logMode .disabled).
final class CieSigner {
    private let api: FasasAPI
    private let cie = CieDigitalId(.disabled)
    private static let digestInfoPrefix: [UInt8] = [0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65,
                                                    0x03, 0x04, 0x02, 0x01, 0x05, 0x00, 0x04, 0x20]

    init(api: FasasAPI) { self.api = api }

    func refuse(_ request: SignRequest) async {
        if let nonce = try? await api.claim(request.id)["nonce"] as? String {
            try? await api.error(request.id, nonce: nonce, code: "cancelled")
        }
    }

    func sign(_ request: SignRequest, pin: String) async -> SignOutcome {
        var nonce = ""
        do {
            let claimed = try await api.claim(request.id)
            guard claimed["verify_code"] as? String == request.verify_code else {
                return .failed(code: "verify_code", message: "Il codice di controllo non coincide: firma interrotta.")
            }
            nonce = claimed["nonce"] as? String ?? ""
            nonce = try await api.state(request.id, nonce: nonce, state: "card")
            cie.setAlertMessage(key: "readingInstructions", value: "Avvicina la CIE alla parte alta del retro dell'iPhone e tienila ferma.")
            let api = self.api
            let requestId = request.id
            let box = NonceBox(nonce)
            let signature = try await cie.performSignature(withPin: pin, prepare: { certificate in
                let prepared = try await api.certificate(requestId, nonce: box.value, certificate: certificate)
                let expected = CieSigner.digestInfoPrefix + Array(SHA256.hash(data: prepared.toBeSigned))
                guard Array(prepared.digestInfo) == expected else {
                    throw ServerError(status: 0, code: "device_error", message: "Dati da firmare incoerenti.")
                }
                box.value = try await api.state(requestId, nonce: prepared.nonce, state: "signing")
                return Array(prepared.digestInfo)
            })
            nonce = box.value
            let result = try await api.sign(request.id, nonce: nonce, signature: signature)
            let level = (result["verification"] as? [String: Any])?["level"] as? String ?? "PAdES"
            return .signed(level: level)
        } catch let error as ServerError {
            return .failed(code: error.code, message: error.message)
        } catch {
            // Errori di CieSDK (PIN errato con tentativi rimasti, carta bloccata, NFC interrotto): da mappare sui
            // codici del FASAS (pin_wrong, pin_blocked, card_removed, cancelled) al collaudo con l'SDK reale.
            let code = Self.code(for: error)
            if !nonce.isEmpty { try? await api.error(request.id, nonce: nonce, code: code) }
            return .failed(code: code, message: String(describing: error))
        }
    }

    private static func code(for error: Error) -> String {
        let text = String(describing: error)
        if text.contains("wrongPin") { return "pin_wrong" }
        if text.contains("cardBlocked") { return "pin_blocked" }
        if text.contains("UserCanceled") { return "cancelled" }
        if text.contains("TagConnectionLost") || text.contains("tagConnectionLost") { return "card_removed" }
        return "device_error"
    }
}

/// Il nonce cambia dentro la sessione NFC (dopo il certificato e dopo «signing").
final class NonceBox: @unchecked Sendable { var value: String; init(_ value: String) { self.value = value } }
