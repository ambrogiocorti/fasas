// FASAS Signer per iPhone – PROTOTIPO: compilato nella CI, non collaudato con una CIE reale.
import SwiftUI

@main
struct FasasSignerApp: App {
    @StateObject private var model = SignerModel()

    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
        }
    }
}
