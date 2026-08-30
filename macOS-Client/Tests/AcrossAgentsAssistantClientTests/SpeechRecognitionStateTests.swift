import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct SpeechRecognitionStateTests {
    @Test
    func stateMachineTranscribesOnlyAfterTheRecordingFinishes() {
        var machine = SpeechRecognitionStateMachine()

        #expect(machine.state == .idle)
        #expect(machine.apply(.startRequested) == .requestingPermission)
        #expect(machine.apply(.captureStarted) == .listening)
        #expect(machine.state.canFinishRecording)
        #expect(machine.apply(.segmentQueued) == .transcribing)
        #expect(!machine.state.canFinishRecording)
        #expect(machine.apply(.segmentTranscribed("Across")) == .segmentTranscript("Across"))
        #expect(machine.state.isActive)
        #expect(machine.apply(.sessionFinished) == .idle)
        #expect(machine.apply(.cancelled) == .cancelled)
        #expect(machine.apply(.retryRequested) == .retrying)
        #expect(machine.apply(.permissionDenied(.microphone)) == .denied(.microphone))
        #expect(machine.apply(.recognizerUnavailable(.audioInputMissing)) == .unavailable(.audioInputMissing))
        #expect(machine.apply(.inputDeviceLost) == .inputDeviceLost)
        #expect(machine.apply(.failed("fixture failure")) == .failed("fixture failure"))
    }

    @Test
    func localVoiceConfigurationNormalizesChineseAndEnglish() {
        let chinese = SpeechRecognitionConfiguration(localeIdentifier: "zh-Hans")
        let english = SpeechRecognitionConfiguration(localeIdentifier: "en_GB")

        #expect(chinese.localeIdentifier == "zh-CN")
        #expect(english.localeIdentifier == "en-US")
    }

    @Test
    func draftMergerKeepsExistingTypedWorkAndAddsEachSegment() {
        #expect(SpeechDraftMerger.merge(existingDraft: "", transcript: "  检查发布证据。  ") == "检查发布证据。")
        #expect(
            SpeechDraftMerger.merge(
                existingDraft: "先运行测试。",
                transcript: "再解释失败原因。"
            ) == "先运行测试。再解释失败原因。"
        )
        #expect(
            SpeechDraftMerger.merge(
                existingDraft: "Review the release.",
                transcript: "Explain the risk."
            ) == "Review the release. Explain the risk."
        )
    }

    @Test
    func transcriptNormalizerUsesSimplifiedChineseOnlyForTheSimplifiedChineseUI() {
        #expect(
            SpeechTranscriptNormalizer.normalizeForComposer(
                "請檢查發佈證據並說明風險。",
                localeIdentifier: "zh-CN"
            ) == "请检查发布证据并说明风险。"
        )
        #expect(
            SpeechTranscriptNormalizer.normalizeForComposer(
                "Review the release evidence.",
                localeIdentifier: "zh-Hans"
            ) == "Review the release evidence."
        )
        #expect(
            SpeechTranscriptNormalizer.normalizeForComposer(
                "請檢查發佈證據。",
                localeIdentifier: "en-US"
            ) == "請檢查發佈證據。"
        )
    }

    @MainActor
    @Test
    func coordinatorPublishesOneFullTranscriptOnlyAfterFinish() async {
        let service = FakeSpeechRecognitionService()
        let coordinator = SpeechInputCoordinator(service: service)
        coordinator.start(existingDraft: "保留已有目标", localeIdentifier: "zh-Hans")
        await Task.yield()

        #expect(coordinator.draftText == nil)
        #expect(coordinator.state.isActive)
        #expect(service.submissionCount == 0)
        coordinator.finish(preservingDraft: coordinator.draftText)
        #expect(service.finishCount == 1)
        service.emit(.segmentTranscript("检查当前发布，并给出证据。"))
        #expect(coordinator.draftText == "保留已有目标，检查当前发布，并给出证据。")
    }

    @MainActor
    @Test
    func editingDuringRecognitionCancelsCaptureAndPreservesTheUsersDraft() async {
        let service = FakeSpeechRecognitionService()
        let coordinator = SpeechInputCoordinator(service: service)
        coordinator.start(existingDraft: "", localeIdentifier: "en-US")
        await Task.yield()

        coordinator.userEditedDraft("inspect this repository carefully")

        #expect(service.cancelCount == 1)
        #expect(coordinator.state == .cancelled)
        #expect(coordinator.draftText == "inspect this repository carefully")
    }

    @MainActor
    @Test
    func retryUsesTheCurrentEditableDraftAndLocale() async {
        let service = FakeSpeechRecognitionService()
        let coordinator = SpeechInputCoordinator(service: service)
        service.emit(.failed("input device unavailable"))

        coordinator.retry(existingDraft: "current draft", localeIdentifier: "zh-Hans")
        await Task.yield()

        #expect(service.retryLocales == ["zh-Hans"])
        coordinator.finish(preservingDraft: coordinator.draftText)
        service.emit(.segmentTranscript("重新连接后继续。"))
        #expect(coordinator.draftText == "current draft 重新连接后继续。")
    }

    @MainActor
    @Test
    func permissionRequestTimesOutToARecoverableCancelledState() async throws {
        let service = PendingPermissionSpeechRecognitionService()
        let coordinator = SpeechInputCoordinator(
            service: service,
            permissionRequestTimeoutNanoseconds: 1_000_000
        )

        coordinator.start(existingDraft: "keep this draft", localeIdentifier: "en-US")
        try await Task.sleep(nanoseconds: 20_000_000)

        #expect(service.cancelCount == 1)
        #expect(coordinator.state == .cancelled)
        #expect(coordinator.draftText == "keep this draft")
    }
}

@MainActor
private final class FakeSpeechRecognitionService: SpeechRecognitionService {
    private(set) var state: SpeechRecognitionState = .idle
    var onStateChange: ((SpeechRecognitionState) -> Void)?
    private(set) var startLocales: [String] = []
    private(set) var retryLocales: [String] = []
    private(set) var cancelCount = 0
    private(set) var finishCount = 0
    private(set) var submissionCount = 0

    func start(localeIdentifier: String) async {
        startLocales.append(localeIdentifier)
        emit(.requestingPermission)
        emit(.listening)
    }

    func retry(localeIdentifier: String) async {
        retryLocales.append(localeIdentifier)
        emit(.retrying)
        emit(.listening)
    }

    func finish() {
        finishCount += 1
        emit(.transcribing)
    }

    func cancel() {
        cancelCount += 1
        emit(.cancelled)
    }

    func emit(_ state: SpeechRecognitionState) {
        self.state = state
        onStateChange?(state)
    }
}

@MainActor
private final class PendingPermissionSpeechRecognitionService: SpeechRecognitionService {
    private(set) var state: SpeechRecognitionState = .idle
    var onStateChange: ((SpeechRecognitionState) -> Void)?
    private(set) var cancelCount = 0

    func start(localeIdentifier: String) async {
        emit(.requestingPermission)
    }

    func retry(localeIdentifier: String) async {
        emit(.requestingPermission)
    }

    func finish() {}

    func cancel() {
        cancelCount += 1
        emit(.cancelled)
    }

    private func emit(_ state: SpeechRecognitionState) {
        self.state = state
        onStateChange?(state)
    }
}
