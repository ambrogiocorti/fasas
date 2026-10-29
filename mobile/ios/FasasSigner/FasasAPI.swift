// FASAS Signer per iOS – PROTOTIPO NON COMPILATO NÉ COLLAUDATO (serve un Mac con Xcode e un iPhone con NFC).
import Foundation

struct ServerError: Error { let status: Int; let code: String; let message: String }

struct SignRequest: Decodable, Sendable {
    let id: String
    let title: String
    let version: Int?
    let document_sha256: String
    let verify_code: String
    let reason: String
}

/// Client delle API /api/firma/v1/ del FASAS: solo HTTPS (App Transport Security), token nell'intestazione Authorization.
final class FasasAPI: @unchecked Sendable {
    private let base: URL
    var token: String

    init(server: String, token: String = "") throws {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespaces)), url.scheme == "https" else {
            throw ServerError(status: 0, code: "https_required", message: "Il FASAS va raggiunto in HTTPS.")
        }
        base = url.appendingPathComponent("api/firma/v1/")
        self.token = token
    }

    private func call(_ method: String, _ path: String, _ body: [String: Any]? = nil, timeout: TimeInterval = 30) async throws -> [String: Any] {
        var request = URLRequest(url: base.appendingPathComponent(path), timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        if status >= 400 {
            throw ServerError(status: status, code: json["error"] as? String ?? "http_error",
                              message: json["message"] as? String ?? "Errore del server (\(status)).")
        }
        return json
    }

    func pair(code: String, name: String) async throws -> String {
        let data = try await call("POST", "abbina/", ["code": code, "name": name, "platform": "ios", "app_version": "0.1"])
        token = data["token"] as? String ?? ""
        return data["user"] as? String ?? ""
    }

    func pending(wait: Int = 10) async throws -> [SignRequest] {
        let data = try await call("GET", "richieste/?attesa=\(wait)", timeout: TimeInterval(30 + wait))
        let raw = try JSONSerialization.data(withJSONObject: data["requests"] ?? [])
        return try JSONDecoder().decode([SignRequest].self, from: raw)
    }

    func claim(_ id: String) async throws -> [String: Any] { try await call("POST", "richieste/\(id)/prendi/") }

    func state(_ id: String, nonce: String, state: String, attemptsLeft: Int? = nil) async throws -> String {
        var body: [String: Any] = ["nonce": nonce, "state": state]
        if let attemptsLeft { body["attempts_left"] = attemptsLeft }
        return try await call("POST", "richieste/\(id)/stato/", body)["nonce"] as? String ?? ""
    }

    func certificate(_ id: String, nonce: String, certificate: [UInt8]) async throws -> (nonce: String, toBeSigned: Data, digestInfo: Data, verifyCode: String) {
        let r = try await call("POST", "richieste/\(id)/certificato/", ["nonce": nonce, "certificate": Data(certificate).base64EncodedString()])
        return (r["nonce"] as? String ?? "", Data(base64Encoded: r["to_be_signed"] as? String ?? "") ?? Data(),
                Data(base64Encoded: r["digest_info"] as? String ?? "") ?? Data(), r["verify_code"] as? String ?? "")
    }

    func sign(_ id: String, nonce: String, signature: [UInt8]) async throws -> [String: Any] {
        try await call("POST", "richieste/\(id)/firma/", ["nonce": nonce, "signature": Data(signature).base64EncodedString()])
    }

    func error(_ id: String, nonce: String, code: String) async throws {
        _ = try await call("POST", "richieste/\(id)/errore/", ["nonce": nonce, "code": code])
    }
}
