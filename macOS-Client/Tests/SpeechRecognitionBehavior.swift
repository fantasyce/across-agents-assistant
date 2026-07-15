import Foundation

private func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

@MainActor
private final class BehaviorSpeechService: SpeechRecognitionService {
    private(set) var state: SpeechRecognitionState = .idle
    var onStateChange: ((SpeechRecognitionState) -> Void)?
    private(set) var starts: [String] = []
    private(set) var retries: [String] = []
    private(set) var finishes = 0
    private(set) var cancellations = 0

    func start(localeIdentifier: String) async {
        starts.append(localeIdentifier)
        emit(.requestingPermission)
        emit(.listening)
    }

    func retry(localeIdentifier: String) async {
        retries.append(localeIdentifier)
        emit(.retrying)
        emit(.listening)
    }

    func finish() {
        finishes += 1
        emit(.transcribing)
    }

    func cancel() {
        cancellations += 1
        emit(.cancelled)
    }

    func emit(_ state: SpeechRecognitionState) {
        self.state = state
        onStateChange?(state)
    }
}

private func pcmFrame(samples: Int, amplitude: Int16) -> Data {
    let values = Array(repeating: amplitude, count: samples)
    return values.withUnsafeBufferPointer { Data(buffer: $0) }
}

@main
struct SpeechRecognitionBehavior {
    @MainActor
    static func main() async {
        var machine = SpeechRecognitionStateMachine()
        check(machine.state == .idle, "Voice input must start idle")
        check(machine.apply(.startRequested) == .requestingPermission, "Start must expose microphone permission")
        check(machine.apply(.captureStarted) == .listening, "Authorized input must keep listening")
        check(machine.state.canFinishRecording, "Only active recording must expose the finish action")
        check(machine.apply(.segmentQueued) == .transcribing, "Explicit finish must start one full-recording transcription")
        check(!machine.state.canFinishRecording, "Transcribing must not expose a second finish action")
        check(machine.apply(.segmentTranscribed("first phrase")) == .segmentTranscript("first phrase"), "The full transcript must become visible")
        check(machine.apply(.sessionFinished) == .idle, "Explicit finish must end the microphone session")
        check(machine.apply(.permissionDenied(.microphone)) == .denied(.microphone), "Microphone denial must be explicit")
        check(machine.apply(.inputDeviceLost) == .inputDeviceLost, "Input device loss must be explicit")
        check(machine.apply(.failed("fixture failure")) == .failed("fixture failure"), "Local engine failures must be explicit")

        check(SpeechRecognitionConfiguration(localeIdentifier: "zh-Hans").localeIdentifier == "zh-CN", "Chinese input must select Chinese local ASR")
        check(SpeechRecognitionConfiguration(localeIdentifier: "en-GB").localeIdentifier == "en-US", "English input must select English local ASR")
        check(
            SpeechTranscriptNormalizer.normalizeForComposer("請檢查發佈證據。", localeIdentifier: "zh-CN") == "请检查发布证据。",
            "Simplified Chinese UI must normalize locally recognized Traditional Chinese"
        )
        check(
            SpeechTranscriptNormalizer.normalizeForComposer("Keep English.", localeIdentifier: "zh-CN") == "Keep English.",
            "Chinese UI must not translate or alter spoken English"
        )

        let recorder = SpeechSessionRecorder(maximumRecordingSeconds: 2)
        let spoken = pcmFrame(samples: 1_600, amplitude: 5_000)
        let silence = pcmFrame(samples: 12_000, amplitude: 0)
        check(recorder.append(spoken) == nil, "Speech onset must keep recording")
        check(recorder.append(silence) == nil, "A pause must not trigger recognition")
        check(recorder.append(spoken) == nil, "Recording must continue after a pause")
        let fullRecording = recorder.finish()
        check(fullRecording?.count == spoken.count * 2 + silence.count, "Explicit finish must return the entire recording once")
        check(recorder.finish() == nil, "A finished recording must not be emitted twice")

        let boundedRecorder = SpeechSessionRecorder(maximumRecordingSeconds: 1)
        check(boundedRecorder.append(pcmFrame(samples: 16_000, amplitude: 5_000)) != nil, "The three-minute production limit must auto-finish through the bounded recorder path")

        let service = BehaviorSpeechService()
        let coordinator = SpeechInputCoordinator(service: service)
        check(service.starts.isEmpty, "Constructing voice input must not request microphone permission")
        coordinator.start(existingDraft: "typed", localeIdentifier: "zh-Hans")
        await Task.yield()
        check(service.starts == ["zh-Hans"], "Only an explicit start may begin voice input")
        check(coordinator.draftText == nil, "Recording must not publish draft text before explicit finish")
        coordinator.finish(preservingDraft: coordinator.draftText)
        check(service.finishes == 1, "Second press must finish rather than discard voice input")
        service.emit(.segmentTranscript("第一段。第二段。"))
        check(coordinator.draftText == "typed 第一段。第二段。", "The full transcript must append once after explicit finish")
        service.emit(.idle)

        coordinator.start(existingDraft: coordinator.draftText ?? "", localeIdentifier: "en-US")
        await Task.yield()
        coordinator.userEditedDraft("user-edited draft")
        check(service.cancellations == 1, "Editing during active capture must protect the user's draft")
        check(coordinator.draftText == "user-edited draft", "Cancellation must preserve the user's edit")

        print("SpeechRecognitionBehavior passed")
    }
}
