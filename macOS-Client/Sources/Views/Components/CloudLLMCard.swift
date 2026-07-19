import SwiftUI

struct CloudLLMCard: View {
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    let llm: LLMConfig
    @Binding var isConfigured: Bool
    @Binding var isExpanded: Bool
    let onSave: (LLMConfig) -> Void
    let onDelete: () -> Void
    let onLoadAPIKey: () async -> String?
    let onRefreshModels: () async -> Void

    @State private var apiKey: String = ""
    @State private var endpoint: String = ""
    @State private var model: String = ""
    @State private var temperature: Double = 0.7
    @State private var maxTokens: Int = 8192
    @State private var showAdvanced: Bool = false
    @State private var showDeleteConfirm: Bool = false
    @State private var isAPIKeyVisible: Bool = false
    @State private var isLoadingAPIKey: Bool = false
    @State private var isRefreshingModels: Bool = false

    private var isSaveDisabled: Bool {
        apiKey.trimmingCharacters(in: .whitespaces).isEmpty ||
        endpoint.trimmingCharacters(in: .whitespaces).isEmpty ||
        model.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var panelColor: Color {
        colorScheme == .dark ? Color(hex: "2c2c2e") : Color.white
    }

    private var fieldColor: Color {
        colorScheme == .dark ? Color(hex: "1c1c1e") : Color(hex: "f3f4f6")
    }

    private var valueTextColor: Color {
        colorScheme == .dark ? Color(hex: "d1d1d6") : .legacyTextLight
    }

    private var labelTextColor: Color {
        colorScheme == .dark ? Color(hex: "636366") : Color(hex: "6b7280")
    }

    private var secondaryTextColor: Color {
        colorScheme == .dark ? Color(hex: "8e8e93") : Color(hex: "6b7280")
    }

    var body: some View {
        VStack(spacing: 0) {
            AgentCard(
                iconName: llm.iconName,
                name: llm.name,
                statusText: isConfigured ? appPreferences.text("models.configured") : appPreferences.text("models.notConfigured"),
                isInstalled: isConfigured,
                accentColor: AcrossTheme.accent,
                isExpanded: isExpanded,
                onTap: { isExpanded.toggle() },
                isCloudLLM: true
            )

            if isExpanded {
                VStack(alignment: .leading, spacing: 12) {
                    detailsContent
                }
                .padding(16)
                .background(panelColor)
                .cornerRadius(10)
                .padding(.top, 0)
                .onAppear {
                    if let key = llm.apiKey, !key.isEmpty {
                        apiKey = key
                    } else {
                        apiKey = ""
                    }
                    isAPIKeyVisible = false
                    endpoint = llm.endpoint ?? ""
                    model = llm.model ?? ""
                }
                .task(id: isExpanded) {
                    guard isExpanded else { return }
                    await loadStoredAPIKeyIfNeeded()
                    if llm.availableModels?.isEmpty != false {
                        await refreshModels()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var detailsContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                HStack(spacing: 2) {
                    Text(appPreferences.text("models.apiKey"))
                        .font(.system(size: 11))
                        .foregroundColor(labelTextColor)
                        .textCase(.uppercase)
                    Text("*")
                        .font(.system(size: 11))
                        .foregroundColor(.red)
                }
                Spacer()
            }

            HStack(spacing: 8) {
                Group {
                    if isAPIKeyVisible {
                        TextField("sk-...", text: $apiKey)
                    } else if !apiKey.isEmpty {
                        Text(maskAPIKey(apiKey))
                            .foregroundColor(valueTextColor)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                Task {
                                    await revealButtonTapped()
                                }
                            }
                    } else {
                        SecureField("sk-...", text: $apiKey)
                    }
                }
                .textFieldStyle(.plain)
                .foregroundColor(valueTextColor)

                if isLoadingAPIKey {
                    ProgressView()
                        .scaleEffect(0.55)
                        .frame(width: 18, height: 18)
                } else {
                    Button(action: {
                        Task {
                            await revealButtonTapped()
                        }
                    }) {
                        Image(systemName: isAPIKeyVisible ? "eye.slash" : "eye")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(secondaryTextColor)
                            .frame(width: 20, height: 20)
                    }
                    .buttonStyle(.plain)
                    .help(isAPIKeyVisible ? appPreferences.text("models.hideApiKey") : appPreferences.text("models.showApiKey"))
                }
            }
            .padding(10)
            .background(fieldColor)
            .cornerRadius(8)
        }

        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 2) {
                Text(appPreferences.text("models.baseURL"))
                    .font(.system(size: 11))
                    .foregroundColor(labelTextColor)
                    .textCase(.uppercase)
                Text("*")
                    .font(.system(size: 11))
                    .foregroundColor(.red)
            }

            TextField(llm.endpoint ?? "auto", text: $endpoint)
                .textFieldStyle(.plain)
                .foregroundColor(valueTextColor)
                .padding(10)
                .background(fieldColor)
                .cornerRadius(8)
        }

        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 2) {
                Text(appPreferences.text("models.model"))
                    .font(.system(size: 11))
                    .foregroundColor(labelTextColor)
                    .textCase(.uppercase)
                Text("*")
                    .font(.system(size: 11))
                    .foregroundColor(.red)
            }

            HStack(spacing: 8) {
                Picker("", selection: $model) {
                    ForEach(availableModels, id: \.self) { m in
                        Text(m).tag(m)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)

                Button(action: {
                    Task {
                        await refreshModels()
                    }
                }) {
                    if isRefreshingModels {
                        ProgressView()
                            .scaleEffect(0.55)
                            .frame(width: 20, height: 20)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(valueTextColor.opacity(0.9))
                            .frame(width: 20, height: 20)
                    }
                }
                .buttonStyle(.plain)
                .help(appPreferences.text("models.refreshModels"))
                .disabled(isRefreshingModels)
            }
            .padding(10)
            .background(fieldColor)
            .cornerRadius(8)
        }

        Button(action: { showAdvanced.toggle() }) {
            HStack {
                Text(appPreferences.text("models.advancedParameters"))
                    .font(.system(size: 12))
                    .foregroundColor(secondaryTextColor)
                Spacer()
                Image(systemName: "chevron.down")
                    .font(.system(size: 10))
                    .foregroundColor(secondaryTextColor)
                    .rotationEffect(.degrees(showAdvanced ? 180 : 0))
            }
            .padding(10)
            .background(fieldColor)
            .cornerRadius(8)
        }

        if showAdvanced {
            VStack(spacing: 8) {
                HStack {
                    Text(appPreferences.text("models.temperature"))
                        .font(.system(size: 12))
                        .foregroundColor(labelTextColor)
                    Spacer()
                    Text(String(format: "%.1f", temperature))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(secondaryTextColor)
                }
                Slider(value: $temperature, in: 0...2, step: 0.1)
                    .tint(AcrossTheme.accent)
            }
            .padding(.top, 8)
        }

        HStack(spacing: 10) {
            Button(appPreferences.text("system.cancel")) {
                isExpanded = false
            }
            .buttonStyle(SecondaryButtonStyle())

            Button(appPreferences.text("system.save")) {
                var updated = llm
                updated.apiKey = apiKey
                updated.endpoint = endpoint
                updated.model = model
                updated.temperature = temperature
                updated.maxTokens = maxTokens
                onSave(updated)
                isExpanded = false
            }
            .buttonStyle(PrimaryButtonStyle(color: AcrossTheme.accent))
            .disabled(isSaveDisabled)

            if isConfigured {
                Button(appPreferences.text("system.delete")) {
                    showDeleteConfirm = true
                }
                .buttonStyle(DestructiveButtonStyle())
                .alert(appPreferences.text("models.deleteConfiguration"), isPresented: $showDeleteConfirm) {
                    Button(appPreferences.text("system.cancel"), role: .cancel) { }
                    Button(appPreferences.text("system.delete"), role: .destructive) {
                        onDelete()
                        isExpanded = false
                    }
                } message: {
                    Text(String(format: appPreferences.text("models.deleteConfiguration.message"), llm.name))
                }
            }
        }
    }

    private var availableModels: [String] {
        var values = llm.availableModels ?? []
        if !model.isEmpty, !values.contains(model) {
            values.insert(model, at: 0)
        }
        if values.isEmpty, let current = llm.model, !current.isEmpty {
            values.append(current)
        }
        return values
    }

    private func loadStoredAPIKeyIfNeeded() async {
        guard isConfigured,
              apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !isLoadingAPIKey else {
            return
        }

        isLoadingAPIKey = true
        if let key = await onLoadAPIKey() {
            apiKey = key
        }
        isLoadingAPIKey = false
    }

    private func revealButtonTapped() async {
        if !isAPIKeyVisible {
            await loadStoredAPIKeyIfNeeded()
        }
        isAPIKeyVisible.toggle()
    }

    private func refreshModels() async {
        guard !isRefreshingModels else { return }
        isRefreshingModels = true
        await onRefreshModels()
        isRefreshingModels = false
    }

    private func maskAPIKey(_ key: String) -> String {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        guard trimmed.count > 10 else { return String(repeating: "*", count: max(trimmed.count, 4)) }

        let prefixLength = min(3, trimmed.count)
        let suffixLength = min(4, max(trimmed.count - prefixLength, 0))
        let prefix = String(trimmed.prefix(prefixLength))
        let suffix = String(trimmed.suffix(suffixLength))
        return "\(prefix)...\(suffix)"
    }
}
