import SwiftUI
import AppKit

struct ModelSettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var expandedCard: String? = nil
    @State private var showingUnconfiguredLocalAgents = false
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

    private var readyLocalAgents: [AgentConfig] {
        viewModel.availableLocalAgents
    }

    private var unconfiguredLocalAgents: [AgentConfig] {
        viewModel.localAgents.filter { !viewModel.isLocalAgentAvailable($0.id) }
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
                ForEach(readyLocalAgents) { agent in
                    localAgentView(agent)
                }
                if readyLocalAgents.isEmpty {
                    MinimalSettingsNotice(
                        text: appPreferences.text("models.localAgent.empty"),
                        color: .secondary,
                        systemImage: "terminal"
                    )
                }
                if !unconfiguredLocalAgents.isEmpty {
                    Button {
                        showingUnconfiguredLocalAgents.toggle()
                    } label: {
                        HStack {
                            Label(
                                "\(appPreferences.text("models.notConfigured")) (\(unconfiguredLocalAgents.count))",
                                systemImage: "plus.circle"
                            )
                            Spacer()
                            Image(systemName: "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                                .rotationEffect(.degrees(showingUnconfiguredLocalAgents ? 180 : 0))
                        }
                        .font(.system(size: 12, weight: .medium))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 10)

                    if showingUnconfiguredLocalAgents {
                        VStack(spacing: 10) {
                            ForEach(unconfiguredLocalAgents) { agent in
                                localAgentView(agent)
                            }
                        }
                        .padding(.bottom, 10)
                    }
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

}
