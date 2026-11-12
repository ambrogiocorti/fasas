// FASAS Signer per iPhone – PROTOTIPO: compilato nella CI, non collaudato con una CIE reale.
import Foundation

struct ServerError: Error, LocalizedError {
    let status: Int
    let code: String
    let message: String
    var errorDescription: String? { message }
}

struct SignRequest: Decodable, Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let version: Int?
    let document_sha256: String
    let verify_code: String
    let reason: String
}

struct Prepared: Sendable {
    let nonce: String
    let toBeSigned: Data
    let digestInfo: Data
    let verifyCode: String
}

/// Client delle API /api/firma/v1/ del FASAS. Solo HTTPS; HTTP solo verso un indirizzo IP della rete locale
/// quando allowLanHttp è attivo (prova con il FASAS sul PC della stessa Wi-Fi). Token nell'intestazione Authorization.
final class FasasAPI: @unchecked Sendable {
    private let base: String
    var token: String

    init(server: String, token: String = "", allowLanHttp: Bool = false) throws {
        let trimmed = server.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), let scheme = url.scheme, let host = url.host else {
            throw ServerError(status: 0, code: "bad_url", message: "Indirizzo del FASAS non valido.")
        }
        let local = ["localhost", "127.0.0.1"].contains(host)
        guard scheme == "https" || (scheme == "http" && (local || (allowLanHttp && FasasAPI.isPrivateIPv4(host)))) else {
            throw ServerError(status: 0, code: "https_required",
                              message: "Il FASAS va raggiunto in HTTPS: con HTTP token e firma viaggerebbero in chiaro.")
        }
        base = (trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed) + "/api/firma/v1/"
        self.token = token
    }

    /// 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 scritti come indirizzo numerico.
    static func isPrivateIPv4(_ host: String) -> Bool {
        let parts = host.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4, parts.allSatisfy({ (0...255).contains($0) }) else { return false }
        return parts[0] == 10 || (parts[0] == 172 && (16...31).contains(parts[1])) || (parts[0] == 192 && parts[1] == 168)
    }

    private func call(_ method: String, _ path: String, _ body: [String: Any]? = nil,
                      timeout: TimeInterval = 30) async throws -> [String: Any] {
        guard let url = URL(string: base + path) else {
            throw ServerError(status: 0, code: "bad_url", message: "Indirizzo non valido.")
        }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw ServerError(status: 0, code: "network", message: "FASAS non raggiungibile: controllare la connessione.")
        }
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

    func me() async throws -> String {
        try await call("GET", "dispositivo/")["user"] as? String ?? ""
    }

    func reportStatus(_ status: [String: Any]) async throws {
        _ = try await call("POST", "dispositivo/stato/", status)
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

    func certificate(_ id: String, nonce: String, certificate: [UInt8]) async throws -> Prepared {
        let r = try await call("POST", "richieste/\(id)/certificato/",
                               ["nonce": nonce, "certificate": Data(certificate).base64EncodedString()])
        return Prepared(nonce: r["nonce"] as? String ?? "",
                        toBeSigned: Data(base64Encoded: r["to_be_signed"] as? String ?? "") ?? Data(),
                        digestInfo: Data(base64Encoded: r["digest_info"] as? String ?? "") ?? Data(),
                        verifyCode: r["verify_code"] as? String ?? "")
    }

    func sign(_ id: String, nonce: String, signature: [UInt8]) async throws -> [String: Any] {
        try await call("POST", "richieste/\(id)/firma/", ["nonce": nonce, "signature": Data(signature).base64EncodedString()])
    }

    func error(_ id: String, nonce: String, code: String) async throws {
        _ = try await call("POST", "richieste/\(id)/errore/", ["nonce": nonce, "code": code])
    }
}
