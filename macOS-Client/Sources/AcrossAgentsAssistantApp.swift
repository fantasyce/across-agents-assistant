import SwiftUI

@main
struct AcrossAgentsAssistantApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VStack {
            Image(systemName: "globe")
                .imageScale(.large)
                .foregroundStyle(.tint)
            Text("Hello, Across Agents Assistant!")
        }
        .padding()
    }
}
