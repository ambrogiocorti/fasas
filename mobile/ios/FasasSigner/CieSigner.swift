// FASAS Signer per iPhone – PROTOTIPO: compilato nella CI, non collaudato con una CIE reale.
// Usa CieSDK (pagopa/cie-sdk-ios, MIT) con la patch patches/cie-sdk-ios-63d2195-performSignature.patch.
import CieSDK
import CoreNFC
import CryptoKit
import Foundation

enum SignOutcome: Equatable {
    case signed(level: String)
    case pinWrong(attemptsLeft: Int?)
    case failed(code: String, message: String)
}

/// Il nonce cambia dentro la sessione NFC (dopo il certificato e dopo «signing»).
final class NonceBox: @unchecked Sendable {
    var value: String
    init(_ value: String) { self.value = value }
}

/// Flusso: conferma → PIN completo (8 cifre) → una sola sessione Core NFC in cui si apre il canale sicuro, si verifica
/// il PIN, si legge il certificato, il FASAS prepara il documento e la carta firma il DigestInfo.
/// Il PIN resta sul telefono e va solo alla carta; CieSDK è usata con i log disattivati.
final class CieSigner {
    private let api: FasasAPI
    private let cie = CieDigitalId(.disabled)
    private var nonce: String?
    private var cardReported = false
    static let digestInfoPrefix: [UInt8] = [0x30, 0x31, 0x30, 0x0d, 0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65,
                                            0x03, 0x04, 0x02, 0x01, 0x05, 0x00, 0x04, 0x20]

    init(api: FasasAPI) {
        self.api = api
        cie.setAlertMessage(key: "readingInstructions",
                            value: "Tieni la CIE sul retro dell'iPhone, nella parte alta, finché la firma non è completata.")
    }

    static var nfcAvailable: Bool { CieDigitalId.isNFCEnabled() }

    func accept(_ request: SignRequest) async throws {
        let claimed = try await api.claim(request.id)
        let claimedNonce = claimed["nonce"] as? String ?? ""
        guard claimed["verify_code"] as? String == request.verify_code else {
            try? await api.error(request.id, nonce: claimedNonce, code: "device_error")
            throw ServerError(status: 0, code: "verify_code", message: "Il codice di controllo non coincide: firma interrotta.")
        }
        nonce = claimedNonce
        cardReported = false
    }

    func refuse(_ request: SignRequest) async {
        if let claimedNonce = try? await api.claim(request.id)["nonce"] as? String {
            try? await api.error(request.id, nonce: claimedNonce, code: "cancelled")
        }
    }

    func cancel(_ request: SignRequest) async {
        if let current = nonce { try? await api.error(request.id, nonce: current, code: "cancelled") }
        nonce = nil
    }

    func sign(_ request: SignRequest, pin: String) async -> SignOutcome {
        guard let start = nonce else { return .failed(code: "bad_state", message: "Richiesta non presa in carico.") }
        let box = NonceBox(start)
        let api = self.api
        let requestId = request.id
        let expectedCode = request.verify_code
        do {
            if !cardReported {
                box.value = try await api.state(requestId, nonce: box.value, state: "card")
                cardReported = true
            }
            let signature = try await cie.performSignature(withPin: pin, prepare: { certificate in
                let prepared = try await api.certificate(requestId, nonce: box.value, certificate: certificate)
                box.value = prepared.nonce
                let expected = CieSigner.digestInfoPrefix + Array(SHA256.hash(data: prepared.toBeSigned))
                guard Array(prepared.digestInfo) == expected, prepared.verifyCode == expectedCode else {
                    throw ServerError(status: 0, code: "device_error", message: "Dati da firmare incoerenti ricevuti dal server.")
                }
                box.value = try await api.state(requestId, nonce: box.value, state: "signing")
                return Array(prepared.digestInfo)
            })
            let result = try await api.sign(requestId, nonce: box.value, signature: signature)
            nonce = nil
            let level = (result["verification"] as? [String: Any])?["level"] as? String ?? "PAdES"
            return .signed(level: level)
        } catch let error as NfcDigitalIdError {
            if case .wrongPin(let left) = error,
               let next = try? await api.state(requestId, nonce: box.value, state: "pin_wrong", attemptsLeft: left) {
                nonce = next
                return .pinWrong(attemptsLeft: left)
            }
            let code = CieSigner.code(for: error)
            try? await api.error(requestId, nonce: box.value, code: code)
            nonce = nil
            return .failed(code: code, message: CieSigner.message(for: code))
        } catch let error as ServerError {
            if error.status == 0 { try? await api.error(requestId, nonce: box.value, code: "device_error") }
            nonce = nil
            return .failed(code: error.code, message: error.message)
        } catch {
            try? await api.error(requestId, nonce: box.value, code: "device_error")
            nonce = nil
            return .failed(code: "device_error", message: error.localizedDescription)
        }
    }

    /// Errori di CieSDK → codici del FASAS (vedi fasas/signatures/cie.py, DEVICE_ERRORS).
    static func code(for error: NfcDigitalIdError) -> String {
        switch error {
        case .wrongPin:
            return "pin_wrong"
        case .cardBlocked:
            return "pin_blocked"
        case .scanNotSupported:
            return "reader_missing"
        case .nfcError(let nfc):
            switch nfc.code {
            case .readerSessionInvalidationErrorUserCanceled:
                return "cancelled"
            case .readerSessionInvalidationErrorSessionTimeout:
                return "timeout"
            default:
                return "card_removed"
            }
        default:
            return "device_error"
        }
    }

    static func message(for code: String) -> String {
        switch code {
        case "pin_blocked": return "PIN della CIE bloccato: sbloccarlo con il PUK dall'app «CIE ID»."
        case "reader_missing": return "Questo iPhone non può leggere la CIE (NFC non disponibile)."
        case "cancelled": return "Firma annullata."
        case "timeout": return "Tempo scaduto: riprovare tenendo la carta ferma sul retro dell'iPhone."
        case "card_removed": return "La carta è stata allontanata: riprovare tenendola ferma."
        default: return "Errore nel dialogo con la CIE."
        }
    }
}
