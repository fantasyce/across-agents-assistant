import SwiftUI
import AppKit

struct ModelSettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var expandedCard: String? = nil
    @State private var showingUnconfiguredProviders = false
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject var appPreferences: AppPreferences
    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false
    var onOpenCapabilities: (String) -> Void = { _ in }

    private var bgColor: Color { Color(nsColor: .windowBackgroundColor) }

    private var configuredCloudLLMs: [LLMConfig] {
        viewModel.cloudLLMs.filter { viewModel.isKeyConfigured($0.id) }
    }

    private var unconfiguredCloudLLMs: [LLMConfig] {
        viewModel.cloudLLMs.filter { !viewModel.isKeyConfigured($0.id) }
    }

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                MinimalSettingsWindowHeader(title: appPreferences.text("models.title"), onClose: onClose)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                    MinimalSettingsPageHeader(title: appPreferences.text("models.title"))
                    localAgentSection
                    cloudLLMSection
                }
                .minimalPageContentFrame()
            }
            .background(bgColor)

            statusFooter
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            Group {
                if !embeddedInHub {
                    VisualEffectView().ignoresSafeArea()
                }
            }
        )
        .ignoresSafeArea(.all, edges: embeddedInHub ? Edge.Set() : .top)
        .onAppear {
            viewModel.loadSettings()
        }
    }

    private var localAgentSection: some View {
        MinimalSettingsSection(title: appPreferences.text("models.localAgent")) {
            VStack(spacing: 10) {
                ForEach(viewModel.localAgents) { agent in
                    localAgentView(agent)
                }
            }
            .padding(.vertical, 10)
        }
    }

    private var cloudLLMSection: some View {
        MinimalSettingsSection(title: appPreferences.text("models.cloudLLM")) {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(configuredCloudLLMs) { llm in
                    cloudLLMView(llm)
                }

                if configuredCloudLLMs.isEmpty {
                    MinimalSettingsNotice(
                        text: appPreferences.text("models.notConfigured"),
                        color: .secondary,
                        systemImage: "cloud"
                    )
                }

                if !unconfiguredCloudLLMs.isEmpty {
                    Button {
                        showingUnconfiguredProviders.toggle()
                    } label: {
                        HStack {
                            Label(
                                "\(appPreferences.text("models.notConfigured")) (\(unconfiguredCloudLLMs.count))",
                                systemImage: "plus.circle"
                            )
                            Spacer()
                            Image(systemName: "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                                .rotationEffect(.degrees(showingUnconfiguredProviders ? 180 : 0))
                        }
                        .font(.system(size: 12, weight: .medium))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 10)

                    if showingUnconfiguredProviders {
                        VStack(spacing: 10) {
                            ForEach(unconfiguredCloudLLMs) { llm in
                                cloudLLMView(llm)
                            }
                        }
                        .padding(.bottom, 10)
                    }
                }
            }
            .padding(.vertical, 10)
        }
    }

    private func localAgentView(_ agent: AgentConfig) -> some View {
        LocalAgentCard(
            agent: agent,
            detectionFeedback: viewModel.localAgentDetectionFeedback[agent.id] ?? .idle,
            isExpanded: Binding(
                get: { expandedCard == agent.id },
                set: { expandedCard = $0 ? agent.id : nil }
            ),
            onSave: viewModel.saveAgentConfig,
            onAutoDetect: viewModel.autoDetectAgent
        )
        .overlay(alignment: .topTrailing) {
            capabilitiesButton(agent.id)
        }
    }

    private func cloudLLMView(_ llm: LLMConfig) -> some View {
        CloudLLMCard(
            llm: llm,
            isConfigured: Binding(
                get: { viewModel.isKeyConfigured(llm.id) },
                set: { _ in }
            ),
            isExpanded: Binding(
                get: { expandedCard == llm.id },
                set: { expandedCard = $0 ? llm.id : nil }
            ),
            onSave: viewModel.saveLLMConfig,
            onDelete: { viewModel.deleteLLMConfig(llm.id) },
            onLoadAPIKey: { await viewModel.loadAPIKeyFromBackend(llm.id) },
            onRefreshModels: { await viewModel.refreshCloudModels(providerId: llm.id) }
        )
        .overlay(alignment: .topTrailing) {
            capabilitiesButton(llm.id)
        }
    }

    private func capabilitiesButton(_ agentID: String) -> some View {
        Button {
            onOpenCapabilities(agentID)
        } label: {
            Image(systemName: "sparkles.rectangle.stack")
                .frame(width: 28, height: 28)
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .padding(.top, 18)
        .padding(.trailing, 42)
        .help(appPreferences.text("models.openCapabilities"))
        .accessibilityLabel(Text(appPreferences.text("models.openCapabilities")))
    }

    // MARK: - Status Footer

    private var statusFooter: some View {
        VStack(spacing: 0) {
            Divider().opacity(0.3)

            HStack(spacing: 0) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(statusIndicators, id: \.id) { indicator in
                            statusDot(indicator: indicator)
                        }
                    }
                }

                Spacer()

                Button(action: { viewModel.checkAll() }) {
                    if viewModel.isCheckingKeys {
                        ProgressView().controlSize(.small).frame(width: 24, height: 24)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .frame(width: 24, height: 24)
                    }
                }
                .buttonStyle(.borderless)
                .disabled(viewModel.isCheckingKeys)
                .help(appPreferences.text("models.refreshAll"))
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 10)
        }
        .background(.bar)
    }

    private var statusIndicators: [StatusIndicator] {
        var items: [StatusIndicator] = []

        for llm in viewModel.cloudLLMs {
            let configured = viewModel.isKeyConfigured(llm.id)
            items.append(StatusIndicator(
                id: "cloud-\(llm.id)",
                label: llm.name,
                isOK: configured
            ))
        }

        for agent in viewModel.localAgents {
            let installed = agent.status == .installed
            items.append(StatusIndicator(
                id: "local-\(agent.id)",
                label: agent.name,
                isOK: installed
            ))
        }

        return items
    }

    private func statusDot(indicator: StatusIndicator) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(indicator.isOK ? Color(nsColor: .systemGreen) : Color(nsColor: .systemOrange))
                .frame(width: 5, height: 5)
            Text(indicator.label)
                .font(.system(size: 10, weight: .regular))
                .foregroundColor(.secondary)
                .lineLimit(1)
        }
    }
}

private struct StatusIndicator {
    let id: String
    let label: String
    let isOK: Bool
}
