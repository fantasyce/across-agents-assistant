import SwiftUI

struct ModelSettingsView: View {
    @State private var deepseekKey: String = ""
    @State private var minimaxKey: String = ""
    @State private var isSaved = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Model Settings")
                .font(.headline)
            
            Text("API keys are securely stored in macOS Keychain.")
                .font(.caption)
                .foregroundColor(.secondary)
            
            VStack(alignment: .leading, spacing: 8) {
                Text("DeepSeek API Key")
                    .font(.caption)
                    .fontWeight(.medium)
                SecureField("sk-...", text: $deepseekKey)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
            }
            
            VStack(alignment: .leading, spacing: 8) {
                Text("MiniMax API Key")
                    .font(.caption)
                    .fontWeight(.medium)
                SecureField("sk-...", text: $minimaxKey)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
            }
            
            HStack {
                Spacer()
                Button(action: saveKeys) {
                    Text(isSaved ? "Saved!" : "Save")
                        .frame(width: 80)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isSaved)
            }
            .padding(.top, 8)
        }
        .padding()
        .frame(width: 320)
        .onAppear(perform: loadKeys)
    }
    
    private func loadKeys() {
        if let key = KeychainManager.shared.getKey(account: "deepseek") {
            deepseekKey = key
        }
        if let key = KeychainManager.shared.getKey(account: "minimax") {
            minimaxKey = key
        }
    }
    
    private func saveKeys() {
        if !deepseekKey.isEmpty {
            KeychainManager.shared.saveKey(key: deepseekKey, account: "deepseek")
        }
        if !minimaxKey.isEmpty {
            KeychainManager.shared.saveKey(key: minimaxKey, account: "minimax")
        }
        
        // Notify backend
        updateBackendKeys()
        
        withAnimation {
            isSaved = true
        }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            isSaved = false
        }
    }
    
    private func updateBackendKeys() {
        guard let url = URL(string: "http://127.0.0.1:8000/api/keys") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: String] = [
            "deepseek": deepseekKey,
            "minimax": minimaxKey
        ]
        
        request.httpBody = try? JSONEncoder().encode(body)
        
        URLSession.shared.dataTask(with: request) { _, _, error in
            if let error = error {
                print("Failed to update backend keys: \(error)")
            } else {
                print("Backend keys updated successfully")
            }
        }.resume()
    }
}
