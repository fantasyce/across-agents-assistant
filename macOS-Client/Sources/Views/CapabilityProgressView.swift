import SwiftUI
import AppKit

struct StarterJourneyView: View {
    let progress: AcrossProductProgressSnapshot
    @ObservedObject var preferences: AppPreferences
    let onOpenModels: () -> Void
    let onOpenPlugins: () -> Void

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(preferences.text("onboarding.firstStep"))
                        .font(.system(size: 28, weight: .semibold))
                    Text(preferences.text("onboarding.firstStep.detail"))
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Button(action: onOpenModels) {
                    Label(preferences.text("onboarding.connectAgent"), systemImage: "plus")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Text(preferences.text("growth.yourCapabilities"))
                            .font(.system(size: 13, weight: .semibold))
                        Spacer()
                        Text("\(progress.unlockedCapabilityCount)/\(progress.capabilities.count)")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.bottom, 10)

                    ForEach(progress.capabilities) { capability in
                        CapabilityStateRow(capability: capability, preferences: preferences)
                        if capability.id != progress.capabilities.last?.id {
                            Divider().padding(.leading, 70)
                        }
                    }
                }
                .padding(16)
                .background(AcrossTheme.recessedFill(for: colorScheme))
                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))

                Button(preferences.text("onboarding.explorePlugins"), action: onOpenPlugins)
                    .buttonStyle(.link)
            }
            .frame(maxWidth: 620, alignment: .leading)
            .padding(.horizontal, 32)
            .padding(.vertical, 64)
            .frame(maxWidth: .infinity)
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
    }
}

struct CapabilityProgressView: View {
    let progress: AcrossProductProgressSnapshot
    @ObservedObject var preferences: AppPreferences
    let onOpenModels: () -> Void
    let onOpenPlugins: () -> Void

    @Environment(\.colorScheme) private var colorScheme

    private var installedCapabilities: [AcrossProductCapability] {
        progress.capabilities.filter(\.isUnlocked)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 30) {
                header
                learningPathSection
                capabilitySection
                achievementSection
            }
            .minimalPageContentFrame()
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
    }

    private var header: some View {
        MinimalPageHeader(
            title: preferences.text("growth.title"),
            subtitle: preferences.text(progress.levelKey)
        ) {}
    }

    private var capabilitySection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(preferences.text("growth.yourCapabilities"))
                .font(.system(size: 17, weight: .semibold))
                .padding(.bottom, 10)
            if installedCapabilities.isEmpty {
                HStack(spacing: 10) {
                    Image(systemName: "puzzlepiece.extension")
                        .foregroundStyle(AcrossTheme.accent)
                        .accessibilityHidden(true)
                    Text(preferences.text("growth.components.empty"))
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button(preferences.text("growth.components.open"), action: onOpenPlugins)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
                .padding(.vertical, 10)
            } else {
                ForEach(installedCapabilities) { capability in
                    CapabilityStateRow(capability: capability, preferences: preferences)
                    if capability.id != installedCapabilities.last?.id {
                        Divider().padding(.leading, 70)
                    }
                }
            }

        }
    }

    private var learningPathSection: some View {
        CapabilityPathView(progress: progress.learning, preferences: preferences)
    }

    private var achievementSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(preferences.text("growth.achievements"))
                    .font(.system(size: 17, weight: .semibold))
                Spacer()
                Text("\(progress.unlockedAchievementCount)/\(progress.achievements.count)")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            .padding(.bottom, 10)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 172, maximum: 210), spacing: 12)],
                alignment: .center,
                spacing: 12
            ) {
                ForEach(progress.achievements) { achievement in
                    AchievementRewardTile(achievement: achievement, preferences: preferences)
                }
            }
        }
    }
}

struct MinimalAutopilotCapabilityView: View {
    @ObservedObject var preferences: AppPreferences
    let onOpenTechnicalDetails: () -> Void

    @StateObject private var viewModel = AutopilotWorkbenchViewModel()
    @Environment(\.colorScheme) private var colorScheme

    private var isActive: Bool {
        guard let summary = viewModel.snapshot?.summary else { return false }
        return summary.schedulerRunning && summary.selfIterationStatus == "active"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(preferences.text("autopilot.simple.title"))
                            .font(.system(size: 28, weight: .semibold))
                        Text(preferences.text("autopilot.simple.subtitle"))
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        Task { await viewModel.load(refresh: true) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.borderless)
                    .help(preferences.text("settings.refresh"))
                }

                statusPanel

                if let error = viewModel.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.system(size: 13))
                        .foregroundStyle(.red)
                } else if let message = viewModel.message {
                    Label(message, systemImage: "checkmark.circle")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }

                HStack(spacing: 12) {
                    Button(action: primaryAction) {
                        Text(preferences.text(isActive ? "autopilot.simple.checkNow" : "autopilot.simple.start"))
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isWorking || viewModel.isLoading)

                    Button(preferences.text("autopilot.simple.details"), action: onOpenTechnicalDetails)
                        .buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: 720, alignment: .leading)
            .padding(.horizontal, 36)
            .padding(.vertical, 40)
            .frame(maxWidth: .infinity)
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .task { await viewModel.load() }
    }

    @ViewBuilder
    private var statusPanel: some View {
        if viewModel.isLoading && viewModel.snapshot == nil {
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text(preferences.text("autopilot.simple.loading"))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 110)
        } else if let summary = viewModel.snapshot?.summary {
            HStack(spacing: 0) {
                statusMetric(
                    preferences.text("autopilot.simple.status"),
                    preferences.text(isActive ? "autopilot.simple.active" : "autopilot.simple.paused"),
                    emphasized: true
                )
                Divider().frame(height: 44)
                statusMetric(preferences.text("autopilot.simple.completed"), "\(summary.completedRunCount)")
                Divider().frame(height: 44)
                statusMetric(
                    preferences.text("autopilot.simple.attention"),
                    "\(summary.failedRunCount + summary.pendingTriggerCount + summary.promotionReadyCount)"
                )
            }
            .padding(.vertical, 22)
            .background(AcrossTheme.recessedFill(for: colorScheme))
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        }
    }

    private func statusMetric(_ title: String, _ value: String, emphasized: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(emphasized && isActive ? Color.green : Color.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
    }

    private func primaryAction() {
        Task {
            if isActive {
                await viewModel.tickTriggers(
                    successMessage: preferences.text("workbench.action.tick.success")
                )
            } else {
                await viewModel.ensureSelfIterationPlan(
                    successMessage: preferences.text("workbench.action.ensure.success")
                )
                if viewModel.errorMessage == nil {
                    await viewModel.startScheduler(
                        successMessage: preferences.text("workbench.action.schedulerStarted.success")
                    )
                }
            }
        }
    }
}

private struct CapabilityPathView: View {
    let progress: AcrossLearningProgressSnapshot
    @ObservedObject var preferences: AppPreferences

    @Environment(\.colorScheme) private var colorScheme

    private var regularMissions: [AcrossLearningMission] {
        progress.missions.filter { !$0.isChallenge }
    }

    private var challenges: [AcrossLearningMission] {
        progress.missions.filter(\.isChallenge)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "map.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(AcrossTheme.accent)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(preferences.text("growth.path.title"))
                        .font(.system(size: 17, weight: .semibold))
                    Text(preferences.text(progress.level.titleKey))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            if let recommended = progress.recommendedMission {
                HStack(spacing: 10) {
                    Image(systemName: recommended.kind.systemImage)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(AcrossTheme.accent)
                        .frame(width: 30, height: 30)
                        .background(AcrossTheme.accent.opacity(0.1))
                        .clipShape(Circle())
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(preferences.text("growth.path.next"))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.secondary)
                        Text(preferences.text(recommended.kind.titleKey))
                            .font(.system(size: 13, weight: .semibold))
                    }
                    Spacer()
                    Image(systemName: "arrow.right")
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
                .padding(11)
                .background(AcrossTheme.accent.opacity(colorScheme == .dark ? 0.14 : 0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .accessibilityElement(children: .combine)
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 112, maximum: 152), spacing: 8)],
                alignment: .leading,
                spacing: 8
            ) {
                ForEach(regularMissions) { mission in
                    missionNode(mission)
                }
            }

            if !challenges.isEmpty {
                HStack(spacing: 8) {
                    Text(preferences.text("growth.challenge.title"))
                        .font(.system(size: 12, weight: .semibold))
                    Rectangle()
                        .fill(AcrossTheme.separator(for: colorScheme))
                        .frame(height: 1)
                }
                HStack(spacing: 8) {
                    ForEach(challenges) { mission in
                        missionNode(mission)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("growth.path.title"))
    }

    private func missionNode(_ mission: AcrossLearningMission) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                PixelAtlasReward(
                    atlas: mission.isChallenge ? .challengeRewards : .journeyNodes,
                    index: missionArtworkIndex(mission),
                    isUnlocked: mission.isAvailable
                )
                .frame(width: 34, height: 34)
                Spacer()
                Image(systemName: mission.isComplete ? "checkmark.circle.fill" : (mission.isAvailable ? "circle" : "lock.fill"))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(mission.isComplete ? Color(hex: "#248A3D") : .secondary)
                    .accessibilityHidden(true)
            }
            Text(preferences.text(mission.kind.titleKey))
                .font(.system(size: 11, weight: .semibold))
                .lineLimit(2)
            Text(preferences.text(mission.kind.detailKey))
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 94, alignment: .topLeading)
        .background(Color.secondary.opacity(mission.isAvailable ? 0.055 : 0.025))
        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        }
        .opacity(mission.isAvailable ? 1 : 0.52)
        .accessibilityElement(children: .combine)
        .accessibilityValue(preferences.text(
            mission.isComplete ? "growth.path.complete" : (mission.isAvailable ? "growth.path.available" : "growth.path.unavailable")
        ))
    }

    private func missionArtworkIndex(_ mission: AcrossLearningMission) -> Int {
        if mission.isChallenge {
            switch mission.kind {
            case .release: return 5
            case .loop: return 6
            default: return 0
            }
        }
        return AcrossLearningMissionKind.allCases.firstIndex(of: mission.kind) ?? 0
    }
}

private struct CapabilityStateRow: View {
    let capability: AcrossProductCapability
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        HStack(spacing: 12) {
            Group {
                if let artworkIndex = capability.artworkIndex {
                    PixelAtlasReward(
                        atlas: .capabilities,
                        index: artworkIndex,
                        isUnlocked: capability.isUnlocked
                    )
                } else {
                    Image(systemName: capability.systemImage)
                        .font(.system(size: 22, weight: .medium))
                        .foregroundStyle(AcrossTheme.accent)
                        .padding(14)
                        .background(Color.secondary.opacity(0.08))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .accessibilityHidden(true)
                }
            }
            .frame(width: 56, height: 56)
            VStack(alignment: .leading, spacing: 3) {
                Text(capability.titleKey.map(preferences.text) ?? capability.title)
                    .font(.system(size: 14, weight: .medium))
                Text(capability.detailKey.map(preferences.text) ?? capability.detail)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer()
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

private struct AchievementRewardTile: View {
    let achievement: AcrossAchievement
    @ObservedObject var preferences: AppPreferences

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(spacing: 10) {
            Group {
                if let artworkIndex = achievement.artworkIndex {
                    PixelAtlasReward(
                        atlas: achievement.usesMilestoneArtwork ? .achievementMilestones : .achievements,
                        index: artworkIndex,
                        isUnlocked: achievement.isUnlocked
                    )
                } else {
                    Image(systemName: achievement.systemImage)
                        .font(.system(size: 30, weight: .medium))
                        .foregroundStyle(AcrossTheme.accent)
                        .padding(20)
                        .background(Color.secondary.opacity(0.08))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .accessibilityHidden(true)
                }
            }
            .frame(width: 96, height: 96)

            Text(achievement.titleKey.map(preferences.text) ?? achievement.title)
                .font(.system(size: 13, weight: .semibold))
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .frame(maxWidth: .infinity, minHeight: 36, alignment: .center)
            if let detailKey = achievement.detailKey {
                Text(preferences.text(detailKey))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, minHeight: 28, alignment: .top)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, minHeight: 210, maxHeight: 210, alignment: .center)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityValue(preferences.text(achievement.isUnlocked ? "growth.rewardEarned" : "growth.rewardLocked"))
    }
}

enum GrowthArtworkAtlas {
    case capabilities
    case achievements
    case achievementMilestones
    case journeyNodes
    case statusCompanions
    case trustSeals
    case challengeRewards

    var image: NSImage? {
        switch self {
        case .capabilities: return GrowthArtwork.capabilities
        case .achievements: return GrowthArtwork.achievements
        case .achievementMilestones: return GrowthArtwork.achievementMilestones
        case .journeyNodes: return GrowthArtwork.journeyNodes
        case .statusCompanions: return GrowthArtwork.statusCompanions
        case .trustSeals: return GrowthArtwork.trustSeals
        case .challengeRewards: return GrowthArtwork.challengeRewards
        }
    }

    var columns: Int {
        switch self {
        case .capabilities: return 2
        case .achievements, .achievementMilestones: return 3
        case .journeyNodes: return 5
        case .statusCompanions, .challengeRewards: return 4
        case .trustSeals: return 2
        }
    }

    var rows: Int { 2 }

    func cellImage(index: Int) -> NSImage? {
        let cells: [NSImage]
        switch self {
        case .capabilities: cells = GrowthArtwork.capabilityCells
        case .achievements: cells = GrowthArtwork.achievementCells
        case .achievementMilestones: cells = GrowthArtwork.achievementMilestoneCells
        case .journeyNodes: cells = GrowthArtwork.journeyNodeCells
        case .statusCompanions: cells = GrowthArtwork.statusCompanionCells
        case .trustSeals: cells = GrowthArtwork.trustSealCells
        case .challengeRewards: cells = GrowthArtwork.challengeRewardCells
        }
        return cells.indices.contains(index) ? cells[index] : nil
    }
}

private enum GrowthArtwork {
    static let capabilities = load("capability-atlas")
    static let achievements = load("achievement-atlas")
    static let achievementMilestones = load("achievement-milestones-atlas", removesBlackBackground: true)
    static let journeyNodes = load("journey-node-atlas")
    static let statusCompanions = load("status-companion-atlas")
    static let trustSeals = load("trust-seal-atlas")
    static let challengeRewards = load("challenge-reward-atlas")
    static let capabilityCells = makeCells(from: capabilities, columns: 2, rows: 2)
    static let achievementCells = makeCells(from: achievements, columns: 3, rows: 2)
    static let achievementMilestoneCells = makeCells(from: achievementMilestones, columns: 3, rows: 2)
    static let journeyNodeCells = makeCells(from: journeyNodes, columns: 5, rows: 2)
    static let statusCompanionCells = makeCells(from: statusCompanions, columns: 4, rows: 2)
    static let trustSealCells = makeCells(from: trustSeals, columns: 2, rows: 2)
    static let challengeRewardCells = makeCells(from: challengeRewards, columns: 4, rows: 2)

    private static func load(_ name: String, removesBlackBackground: Bool = false) -> NSImage? {
        guard let url = bundledAssetURL(
            named: name,
            withExtension: "png",
            subdirectory: "Assets/growth"
        ) else {
            return nil
        }
        guard let image = NSImage(contentsOf: url) else { return nil }
        return removesBlackBackground ? image.removingNearBlackBackground() : image
    }

    private static func makeCells(from image: NSImage?, columns: Int, rows: Int) -> [NSImage] {
        guard let image else { return [] }
        let cellWidth = image.size.width / CGFloat(columns)
        let cellHeight = image.size.height / CGFloat(rows)
        return (0..<(columns * rows)).map { index in
            let column = CGFloat(index % columns)
            let row = CGFloat(index / columns)
            let sourceRect = NSRect(
                x: column * cellWidth,
                y: image.size.height - ((row + 1) * cellHeight),
                width: cellWidth,
                height: cellHeight
            )
            let cell = NSImage(size: NSSize(width: cellWidth, height: cellHeight), flipped: false) { destination in
                image.draw(
                    in: destination,
                    from: sourceRect,
                    operation: .copy,
                    fraction: 1,
                    respectFlipped: true,
                    hints: [.interpolation: NSImageInterpolation.none]
                )
                return true
            }
            return cell.trimmingTransparentMargins()
        }
    }
}

private extension NSImage {
    func removingNearBlackBackground(threshold: UInt8 = 12) -> NSImage {
        guard let source = cgImage(forProposedRect: nil, context: nil, hints: nil) else { return self }
        let width = source.width
        let height = source.height
        let bytesPerRow = width * 4
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * height)
        guard let context = CGContext(
            data: &pixels,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return self }

        context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        for offset in stride(from: 0, to: pixels.count, by: 4) {
            if pixels[offset] <= threshold,
               pixels[offset + 1] <= threshold,
               pixels[offset + 2] <= threshold {
                pixels[offset + 3] = 0
            }
        }

        guard let output = context.makeImage() else { return self }
        return NSImage(cgImage: output, size: size)
    }

    func trimmingTransparentMargins(alphaThreshold: UInt8 = 8) -> NSImage {
        guard let source = cgImage(forProposedRect: nil, context: nil, hints: nil) else { return self }
        let width = source.width
        let height = source.height
        let bytesPerRow = width * 4
        var pixels = [UInt8](repeating: 0, count: bytesPerRow * height)
        guard let context = CGContext(
            data: &pixels,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return self }
        context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))

        var minX = width
        var minY = height
        var maxX = -1
        var maxY = -1
        for y in 0..<height {
            for x in 0..<width {
                let alpha = pixels[(y * bytesPerRow) + (x * 4) + 3]
                guard alpha > alphaThreshold else { continue }
                minX = min(minX, x)
                minY = min(minY, y)
                maxX = max(maxX, x)
                maxY = max(maxY, y)
            }
        }
        guard maxX >= minX, maxY >= minY, let rendered = context.makeImage() else { return self }

        let padding = 3
        let cropX = max(0, minX - padding)
        let cropY = max(0, minY - padding)
        let cropMaxX = min(width - 1, maxX + padding)
        let cropMaxY = min(height - 1, maxY + padding)
        let cropRect = CGRect(
            x: cropX,
            y: cropY,
            width: cropMaxX - cropX + 1,
            height: cropMaxY - cropY + 1
        )
        guard let cropped = rendered.cropping(to: cropRect) else { return self }
        return NSImage(
            cgImage: cropped,
            size: NSSize(width: cropRect.width, height: cropRect.height)
        )
    }
}

struct PixelAtlasReward: View {
    let atlas: GrowthArtworkAtlas
    let index: Int
    let isUnlocked: Bool

    var body: some View {
        Group {
            if let image = atlas.cellImage(index: index) {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.none)
                    .scaledToFit()
            } else {
                Image(systemName: "star.square.fill")
                    .resizable()
                    .scaledToFit()
                    .foregroundStyle(.secondary)
                    .padding(12)
            }
        }
        .saturation(isUnlocked ? 1 : 0)
        .opacity(isUnlocked ? 1 : 0.32)
        .accessibilityHidden(true)
    }
}
