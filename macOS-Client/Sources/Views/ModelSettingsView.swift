import SwiftUI
import AppKit

struct ModelSettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var expandedCard: String? = nil
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject var appPreferences: AppPreferences
    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var footerButtonBackground: Color { colorScheme == .dark ? Color(hex: "2c2c2e") : Color.white }
    private var footerButtonBorder: Color { colorScheme == .dark ? Color.white.opacity(0.06) : Color.black.opacity(0.08) }
    private var footerButtonText: Color { colorScheme == .dark ? Color(hex: "a0a0a5") : Color(hex: "4b5563") }
    private var footerMutedText: Color { colorScheme == .dark ? Color(hex: "636366") : Color(hex: "9ca3af") }

    var body: some View {
        VStack(spacing: 0) {
            // Header with traffic lights
            if !embeddedInHub {
                HStack {
                    CustomTrafficLights(onClose: onClose)

                    Spacer()

                    Text(appPreferences.text("models.title"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(textColor)

                    Spacer()

                    Spacer().frame(width: 50)
                }
                .padding(.horizontal, 16)
                .frame(height: 56)
                .background(
                    ZStack {
                        bgColor.opacity(0.8)
                        WindowDragView()
                            .contentShape(Rectangle())
                    }
                )

                Divider().opacity(0.5)
            }

            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
                    pageTitle

                    HStack(alignment: .top, spacing: 24) {
                        localAgentColumn
                        cloudLLMColumn
                    }
                }
                .padding(SettingsHubPageLayout.contentPadding)
                .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .background(bgColor)

            // Status footer
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

    private var pageTitle: some View {
        Text(appPreferences.text("models.title"))
            .font(.system(size: 28, weight: .bold))
            .foregroundColor(textColor)
            .padding(.top, 2)
    }

    private var localAgentColumn: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(appPreferences.text("models.localAgent"))
                .font(.system(size: 10, weight: .semibold))
                .tracking(1)
                .foregroundColor(Color(hex: "d97757"))
                .padding(.leading, 4)
                .padding(.bottom, 8)

            ForEach(viewModel.localAgents) { agent in
                LocalAgentCard(
                    agent: agent,
                    detectionFeedback: viewModel.localAgentDetectionFeedback[agent.id] ?? .idle,
                    isExpanded: Binding(
                        get: { expandedCard == agent.id },
                        set: { expanded in
                            expandedCard = expanded ? agent.id : nil
                        }
                    ),
                    onSave: { config in
                        viewModel.saveAgentConfig(config)
                    },
                    onAutoDetect: { agentId in
                        viewModel.autoDetectAgent(agentId)
                    },
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var cloudLLMColumn: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(appPreferences.text("models.cloudLLM"))
                .font(.system(size: 10, weight: .semibold))
                .tracking(1)
                .foregroundColor(Color(hex: "4d6bfe"))
                .padding(.leading, 4)
                .padding(.bottom, 8)

            ForEach(viewModel.cloudLLMs) { llm in
                CloudLLMCard(
                    llm: llm,
                    isConfigured: Binding(
                        get: { viewModel.isKeyConfigured(llm.id) },
                        set: { _ in }
                    ),
                    isExpanded: Binding(
                        get: { expandedCard == llm.id },
                        set: { expanded in
                            expandedCard = expanded ? llm.id : nil
                        }
                    ),
                    onSave: { config in
                        viewModel.saveLLMConfig(config)
                    },
                    onDelete: {
                        viewModel.deleteLLMConfig(llm.id)
                    },
                    onLoadAPIKey: {
                        await viewModel.loadAPIKeyFromBackend(llm.id)
                    }
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Status Footer

    private var statusFooter: some View {
        VStack(spacing: 0) {
            Divider().opacity(0.3)

            HStack(spacing: 0) {
                // Status dots row
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(statusIndicators, id: \.label) { indicator in
                            statusDot(indicator: indicator)
                        }
                    }
                }

                Spacer()

                // Refresh button
                Button(action: { viewModel.checkAll() }) {
                    HStack(spacing: 5) {
                        if viewModel.isCheckingKeys {
                            ProgressView()
                                .scaleEffect(0.55)
                                .frame(width: 10, height: 10)
                        }
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 10, weight: .medium))
                        Text(appPreferences.text("models.refreshAll"))
                            .font(.system(size: 10, weight: .medium))
                    }
                    .foregroundColor(viewModel.isCheckingKeys ? footerMutedText : footerButtonText)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(
                        Capsule()
                            .fill(footerButtonBackground)
                    )
                    .overlay(
                        Capsule()
                            .stroke(footerButtonBorder, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isCheckingKeys)
                .scaleEffect(viewModel.isCheckingKeys ? 0.97 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: viewModel.isCheckingKeys)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 10)
        }
        .background(bgColor)
    }

    private var statusIndicators: [StatusIndicator] {
        var items: [StatusIndicator] = []

        for llm in viewModel.cloudLLMs {
            let configured = viewModel.isKeyConfigured(llm.id)
            items.append(StatusIndicator(
                label: llm.id == "deepseek" ? "Deepseek" : "MiniMax",
                isOK: configured
            ))
        }

        for agent in viewModel.localAgents {
            let installed = agent.status == .installed
            items.append(StatusIndicator(
                label: agent.name,
                isOK: installed
            ))
        }

        return items
    }

    private func statusDot(indicator: StatusIndicator) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(indicator.isOK ? Color(hex: "30d158") : Color(hex: "ff9f0a"))
                .frame(width: 5, height: 5)
            Text(indicator.label)
                .font(.system(size: 10, weight: .regular))
                .foregroundColor(colorScheme == .dark ? Color(hex: "8e8e93") : Color(hex: "6b7280"))
        }
    }
}

private struct StatusIndicator {
    let label: String
    let isOK: Bool
}
