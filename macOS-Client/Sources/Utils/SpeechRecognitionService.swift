@preconcurrency import AVFoundation
import Combine
import Foundation

enum SpeechPermissionKind: String, Equatable, Sendable {
    case microphone
}

enum SpeechRecognitionUnavailableReason: Equatable, Sendable {
    case audioInputMissing
    case localEngineUnavailable
}

enum SpeechRecognitionState: Equatable, Sendable {
    case idle
    case requestingPermission
    case denied(SpeechPermissionKind)
    case unavailable(SpeechRecognitionUnavailableReason)
    case listening
    case transcribing
    case segmentTranscript(String)
    case cancelled
    case inputDeviceLost
    case failed(String)
    case retrying

    var isActive: Bool {
        switch self {
        case .requestingPermission, .listening, .transcribing, .segmentTranscript, .retrying:
            return true
        default:
            return false
        }
    }

    var canRetry: Bool {
        switch self {
        case .denied, .unavailable, .cancelled, .inputDeviceLost, .failed:
            return true
        default:
            return false
        }
    }

    var canFinishRecording: Bool {
        if case .listening = self { return true }
        return false
    }

    var isTranscriptReady: Bool {
        if case .segmentTranscript = self { return true }
        return false
    }

    func shortStatus(localeIdentifier: String) -> String? {
        let isChinese = localeIdentifier.lowercased().hasPrefix("zh")
        switch self {
        case .idle:
            return nil
        case .requestingPermission:
            return isChinese ? "等待麦克风" : "Microphone"
        case .denied:
            return isChinese ? "需要麦克风" : "Microphone needed"
        case .unavailable:
            return isChinese ? "语音不可用" : "Unavailable"
        case .listening:
            return isChinese ? "正在聆听" : "Listening"
        case .transcribing:
            return isChinese ? "正在识别" : "Transcribing"
        case .segmentTranscript:
            return isChinese ? "已完成" : "Ready"
        case .cancelled:
            return isChinese ? "已取消" : "Cancelled"
        case .inputDeviceLost:
            return isChinese ? "麦克风已断开" : "Microphone lost"
        case .failed:
            return isChinese ? "语音失败" : "Voice input failed"
        case .retrying:
            return isChinese ? "正在重试" : "Retrying"
        }
    }

    func accessibilityDetail(localeIdentifier: String) -> String {
        let isChinese = localeIdentifier.lowercased().hasPrefix("zh")
        switch self {
        case .idle:
            return isChinese ? "语音输入空闲" : "Voice input idle"
        case .requestingPermission:
            return isChinese ? "正在请求麦克风权限" : "Requesting microphone permission"
        case .denied:
            return isChinese ? "麦克风权限未开启；可在系统设置中开启后重试" : "Microphone permission is off; enable it in System Settings, then retry"
        case .unavailable(.audioInputMissing):
            return isChinese ? "没有可用的麦克风" : "No microphone is available"
        case .unavailable(.localEngineUnavailable):
            return isChinese ? "本地语音引擎当前不可用" : "The local voice engine is unavailable"
        case .listening:
            return isChinese ? "正在持续录音；中途停顿不会开始识别，再次点击后统一转写" : "Recording continuously; pauses do not start transcription, press again to transcribe everything"
        case .transcribing:
            return isChinese ? "录音已结束，正在本地识别整段语音" : "Recording ended; transcribing the full recording locally"
        case .segmentTranscript:
            return isChinese ? "整段语音已加入可编辑草稿" : "The full recording was added to the editable draft"
        case .cancelled:
            return isChinese ? "语音输入已取消；点击可重新开始" : "Voice input cancelled; press to start again"
        case .inputDeviceLost:
            return isChinese ? "麦克风连接已中断；重新连接后点击重试" : "The microphone was disconnected; reconnect it, then retry"
        case .failed(let message):
            return isChinese ? "语音输入失败：\(message)；点击可重试" : "Voice input failed: \(message); press to retry"
        case .retrying:
            return isChinese ? "正在重新启动本地语音输入" : "Restarting local voice input"
        }
    }
}

enum SpeechRecognitionEvent: Equatable, Sendable {
    case startRequested
    case permissionDenied(SpeechPermissionKind)
    case recognizerUnavailable(SpeechRecognitionUnavailableReason)
    case captureStarted
    case segmentQueued
    case segmentTranscribed(String)
    case sessionFinished
    case cancelled
    case inputDeviceLost
    case failed(String)
    case retryRequested
}

struct SpeechRecognitionStateMachine: Sendable {
    private(set) var state: SpeechRecognitionState = .idle

    @discardableResult
    mutating func apply(_ event: SpeechRecognitionEvent) -> SpeechRecognitionState {
        switch event {
        case .startRequested:
            state = .requestingPermission
        case .permissionDenied(let permission):
            state = .denied(permission)
        case .recognizerUnavailable(let reason):
            state = .unavailable(reason)
        case .captureStarted:
            state = .listening
        case .segmentQueued:
            state = .transcribing
        case .segmentTranscribed(let text):
            state = .segmentTranscript(text)
        case .sessionFinished:
            state = .idle
        case .cancelled:
            state = .cancelled
        case .inputDeviceLost:
            state = .inputDeviceLost
        case .failed(let message):
            state = .failed(message)
        case .retryRequested:
            state = .retrying
        }
        return state
    }
}

struct SpeechRecognitionConfiguration: Equatable, Sendable {
    let localeIdentifier: String

    init(localeIdentifier: String) {
        self.localeIdentifier = Self.recognitionLocaleIdentifier(for: localeIdentifier)
    }

    static func recognitionLocaleIdentifier(for appLocaleIdentifier: String) -> String {
        let normalized = appLocaleIdentifier.replacingOccurrences(of: "_", with: "-").lowercased()
        if normalized.hasPrefix("zh") {
            return "zh-CN"
        }
        if normalized.hasPrefix("en") {
            return "en-US"
        }
        return appLocaleIdentifier.isEmpty ? "en-US" : appLocaleIdentifier
    }
}

@MainActor
protocol SpeechRecognitionService: AnyObject {
    var state: SpeechRecognitionState { get }
    var onStateChange: ((SpeechRecognitionState) -> Void)? { get set }

    func start(localeIdentifier: String) async
    func retry(localeIdentifier: String) async
    func finish()
    func cancel()
}

enum SpeechDraftMerger {
    static func merge(existingDraft: String, transcript: String) -> String {
        let cleanedTranscript = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanedTranscript.isEmpty else { return existingDraft }
        guard !existingDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return cleanedTranscript
        }
        if existingDraft.last?.isWhitespace == true {
            return existingDraft + cleanedTranscript
        }

        let existingLast = existingDraft.last
        let transcriptFirst = cleanedTranscript.first
        let existingEndsWithChinesePhrase = existingLast.map(isCJK) == true
            || (
                existingLast.map(isPunctuation) == true
                    && existingDraft.dropLast().last.map(isCJK) == true
            )
        let joinsTwoChinesePhrases = existingEndsWithChinesePhrase
            && transcriptFirst.map(isCJK) == true
        if joinsTwoChinesePhrases {
            let separator = existingLast.map(isPunctuation) == true ? "" : "，"
            return existingDraft + separator + cleanedTranscript
        }
        return existingDraft + " " + cleanedTranscript
    }

    private static func isCJK(_ character: Character) -> Bool {
        character.unicodeScalars.contains { scalar in
            switch scalar.value {
            case 0x3400...0x4DBF, 0x4E00...0x9FFF, 0x20000...0x2FA1F:
                return true
            default:
                return false
            }
        }
    }

    private static func isPunctuation(_ character: Character) -> Bool {
        character.unicodeScalars.allSatisfy {
            CharacterSet.punctuationCharacters.contains($0)
        }
    }
}

enum SpeechTranscriptNormalizer {
    static func normalizeForComposer(_ transcript: String, localeIdentifier: String) -> String {
        let normalizedLocale = localeIdentifier
            .replacingOccurrences(of: "_", with: "-")
            .lowercased()
        guard normalizedLocale.hasPrefix("zh-cn") || normalizedLocale.hasPrefix("zh-hans") else {
            return transcript
        }
        return transcript.applyingTransform(
            StringTransform("Traditional-Simplified"),
            reverse: false
        ) ?? transcript
    }
}

@MainActor
final class SpeechInputCoordinator: ObservableObject {
    @Published private(set) var state: SpeechRecognitionState = .idle
    @Published private(set) var draftText: String?

    private let service: any SpeechRecognitionService
    private let permissionRequestTimeoutNanoseconds: UInt64
    private var workingDraft = ""
    private var permissionTimeoutTask: Task<Void, Never>?

    init(
        service: (any SpeechRecognitionService)? = nil,
        permissionRequestTimeoutNanoseconds: UInt64 = 12_000_000_000
    ) {
        let resolvedService = service ?? NativeSpeechRecognitionService()
        self.service = resolvedService
        self.permissionRequestTimeoutNanoseconds = permissionRequestTimeoutNanoseconds
        self.state = resolvedService.state
        resolvedService.onStateChange = { [weak self] state in
            self?.receive(state)
        }
    }

    func start(existingDraft: String, localeIdentifier: String) {
        workingDraft = existingDraft
        draftText = nil
        Task { await service.start(localeIdentifier: localeIdentifier) }
        schedulePermissionTimeout()
    }

    func retry(existingDraft: String, localeIdentifier: String) {
        workingDraft = existingDraft
        draftText = nil
        Task { await service.retry(localeIdentifier: localeIdentifier) }
        schedulePermissionTimeout()
    }

    func finish(preservingDraft draft: String? = nil) {
        if let draft {
            workingDraft = draft
        }
        service.finish()
    }

    func cancel(preservingDraft draft: String? = nil) {
        if let draft {
            workingDraft = draft
        }
        service.cancel()
        draftText = workingDraft
    }

    private func schedulePermissionTimeout() {
        permissionTimeoutTask?.cancel()
        let timeout = permissionRequestTimeoutNanoseconds
        permissionTimeoutTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: timeout)
            guard !Task.isCancelled, self?.state == .requestingPermission else { return }
            self?.service.cancel()
        }
    }

    func userEditedDraft(_ draft: String) {
        guard state.isActive, draftText != draft else { return }
        cancel(preservingDraft: draft)
    }

    private func receive(_ state: SpeechRecognitionState) {
        self.state = state
        if state != .requestingPermission && state != .retrying {
            permissionTimeoutTask?.cancel()
            permissionTimeoutTask = nil
        }
        switch state {
        case .segmentTranscript(let transcript):
            workingDraft = SpeechDraftMerger.merge(existingDraft: workingDraft, transcript: transcript)
            draftText = workingDraft
        case .cancelled:
            draftText = workingDraft
        default:
            break
        }
    }
}

private enum MicrophoneAuthorizationResult: Equatable {
    case authorized
    case denied
}

private protocol MicrophonePermissionProviding: AnyObject {
    func requestMicrophoneAuthorization() async -> MicrophoneAuthorizationResult
}

private final class SystemMicrophonePermissionProvider: MicrophonePermissionProviding {
    func requestMicrophoneAuthorization() async -> MicrophoneAuthorizationResult {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return .authorized
        case .denied, .restricted:
            return .denied
        case .notDetermined:
            let granted = await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .audio) { granted in
                    continuation.resume(returning: granted)
                }
            }
            return granted ? .authorized : .denied
        @unknown default:
            return .denied
        }
    }
}

private protocol LocalVoiceTranscribing: Sendable {
    func transcribe(
        pcm16le: Data,
        sampleRateHz: Int,
        localeIdentifier: String
    ) async throws -> String
}

private struct LocalVoiceTranscriptionClient: LocalVoiceTranscribing {
    private struct RequestBody: Encodable {
        let pcm16leBase64: String
        let sampleRateHz: Int
        let localeIdentifier: String

        enum CodingKeys: String, CodingKey {
            case pcm16leBase64 = "pcm16le_base64"
            case sampleRateHz = "sample_rate_hz"
            case localeIdentifier = "locale_identifier"
        }
    }

    private struct ResponseBody: Decodable {
        let transcript: String
    }

    func transcribe(
        pcm16le: Data,
        sampleRateHz: Int,
        localeIdentifier: String
    ) async throws -> String {
        guard let url = URL(string: "http://backend/api/voice/transcribe") else {
            throw VoiceClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        // A three-minute recording can take longer than real time to decode on
        // older Macs. Keep the request bounded without cutting off valid work.
        request.timeoutInterval = 300
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(
            RequestBody(
                pcm16leBase64: pcm16le.base64EncodedString(),
                sampleRateHz: sampleRateHz,
                localeIdentifier: localeIdentifier
            )
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw VoiceClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw VoiceClientError.serviceUnavailable
        }
        let transcript = try JSONDecoder().decode(ResponseBody.self, from: data).transcript
        return SpeechTranscriptNormalizer.normalizeForComposer(
            transcript,
            localeIdentifier: localeIdentifier
        )
    }
}

private enum VoiceClientError: LocalizedError {
    case invalidEndpoint
    case invalidResponse
    case serviceUnavailable

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint, .invalidResponse:
            return "Local voice input is unavailable"
        case .serviceUnavailable:
            return "Local voice input is preparing"
        }
    }
}

/// Keeps the complete microphone session in memory until the user explicitly
/// finishes. Pauses never trigger recognition; the bounded full recording is
/// transcribed once so punctuation, context, and mixed languages stay intact.
final class SpeechSessionRecorder: @unchecked Sendable {
    private let maximumRecordingSamples: Int
    private let lock = NSLock()
    private var frames: [Data] = []
    private var sampleCount = 0
    private var isClosed = false

    init(maximumRecordingSeconds: Int = 180) {
        maximumRecordingSamples = 16_000 * max(1, maximumRecordingSeconds)
    }

    func append(_ frame: Data) -> Data? {
        let frameSamples = frame.count / MemoryLayout<Int16>.size
        guard frameSamples > 0 else { return nil }
        lock.lock()
        defer { lock.unlock() }
        guard !isClosed else { return nil }

        let remainingSamples = maximumRecordingSamples - sampleCount
        guard remainingSamples > 0 else { return closeLocked() }
        let acceptedSamples = min(frameSamples, remainingSamples)
        frames.append(frame.prefix(acceptedSamples * MemoryLayout<Int16>.size))
        sampleCount += acceptedSamples
        return sampleCount >= maximumRecordingSamples ? closeLocked() : nil
    }

    func finish() -> Data? {
        lock.lock()
        defer { lock.unlock() }
        return closeLocked()
    }

    func reset() {
        lock.lock()
        defer { lock.unlock() }
        frames.removeAll(keepingCapacity: false)
        sampleCount = 0
        isClosed = false
    }

    private func closeLocked() -> Data? {
        guard !isClosed, !frames.isEmpty else { return nil }
        isClosed = true
        var pcm = Data()
        pcm.reserveCapacity(frames.reduce(0) { $0 + $1.count })
        for frame in frames {
            pcm.append(frame)
        }
        return pcm
    }
}

@MainActor
final class NativeSpeechRecognitionService: SpeechRecognitionService {
    private(set) var state: SpeechRecognitionState = .idle
    var onStateChange: ((SpeechRecognitionState) -> Void)?

    private let permissionProvider: any MicrophonePermissionProviding
    private let transcriber: any LocalVoiceTranscribing
    private let recorder = SpeechSessionRecorder()
    private var stateMachine = SpeechRecognitionStateMachine()
    private var audioEngine: AVAudioEngine?
    private var pcmConverter: AVAudioConverter?
    private var pcmFormat: AVAudioFormat?
    private var audioConfigurationObserver: NSObjectProtocol?
    private var hasInputTap = false
    private var activeSessionID: UUID?
    private var lastLocaleIdentifier = "en-US"
    private var transcriptionTask: Task<Void, Never>?
    private var isFinishing = false

    init() {
        self.permissionProvider = SystemMicrophonePermissionProvider()
        self.transcriber = LocalVoiceTranscriptionClient()
    }

    private init(
        permissionProvider: any MicrophonePermissionProviding,
        transcriber: any LocalVoiceTranscribing
    ) {
        self.permissionProvider = permissionProvider
        self.transcriber = transcriber
    }

    func start(localeIdentifier: String) async {
        stopCapture(discardPending: true)
        let sessionID = UUID()
        activeSessionID = sessionID
        lastLocaleIdentifier = SpeechRecognitionConfiguration(localeIdentifier: localeIdentifier).localeIdentifier
        isFinishing = false
        recorder.reset()
        transition(.startRequested)

        let authorization = await permissionProvider.requestMicrophoneAuthorization()
        guard activeSessionID == sessionID else { return }
        guard authorization == .authorized else {
            activeSessionID = nil
            transition(.permissionDenied(.microphone))
            return
        }
        beginCapture(sessionID: sessionID)
    }

    func retry(localeIdentifier: String) async {
        transition(.retryRequested)
        await start(localeIdentifier: localeIdentifier.isEmpty ? lastLocaleIdentifier : localeIdentifier)
    }

    func finish() {
        guard let sessionID = activeSessionID else { return }
        finishRecording(recorder.finish(), sessionID: sessionID)
    }

    func cancel() {
        activeSessionID = nil
        isFinishing = false
        recorder.reset()
        stopCapture(discardPending: true)
        transition(.cancelled)
    }

    private func beginCapture(sessionID: UUID) {
        let engine = AVAudioEngine()
        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)
        guard inputFormat.channelCount > 0, inputFormat.sampleRate > 0,
              let outputFormat = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: Double(VOICE_SAMPLE_RATE_HZ),
                channels: 1,
                interleaved: true
              ),
              let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else {
            activeSessionID = nil
            transition(.recognizerUnavailable(.audioInputMissing))
            return
        }

        audioEngine = engine
        pcmConverter = converter
        pcmFormat = outputFormat
        inputNode.installTap(onBus: 0, bufferSize: 1_024, format: inputFormat) { [weak self, weak converter, weak outputFormat] buffer, _ in
            guard let self, let converter, let outputFormat,
                  let pcm16le = Self.convertToPCM16(buffer, converter: converter, outputFormat: outputFormat)
            else { return }
            if let completedRecording = self.recorder.append(pcm16le) {
                Task { @MainActor [weak self] in
                    self?.finishRecording(completedRecording, sessionID: sessionID)
                }
            }
        }
        hasInputTap = true

        audioConfigurationObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: engine,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.handleInputDeviceLoss(sessionID: sessionID)
            }
        }

        engine.prepare()
        do {
            try engine.start()
            transition(.captureStarted)
        } catch {
            activeSessionID = nil
            stopCapture(discardPending: true)
            transition(.failed("Microphone could not start"))
        }
    }

    private func finishRecording(_ recording: Data?, sessionID: UUID) {
        guard activeSessionID == sessionID, !isFinishing else { return }
        isFinishing = true
        stopCapture(discardPending: false)
        guard let recording, !recording.isEmpty else {
            finishIfReady()
            return
        }
        let localeIdentifier = lastLocaleIdentifier
        let transcriber = self.transcriber
        transition(.segmentQueued)
        transcriptionTask = Task { [weak self] in
            do {
                let transcript = try await transcriber.transcribe(
                    pcm16le: recording,
                    sampleRateHz: VOICE_SAMPLE_RATE_HZ,
                    localeIdentifier: localeIdentifier
                )
                guard !Task.isCancelled else { return }
                self?.completeTranscription(transcript, sessionID: sessionID)
            } catch is CancellationError {
                // Cancelling voice input deliberately abandons in-flight audio.
            } catch {
                guard !Task.isCancelled else { return }
                self?.failTranscription(sessionID: sessionID)
            }
        }
    }

    private func completeTranscription(_ transcript: String, sessionID: UUID) {
        transcriptionTask = nil
        guard activeSessionID == sessionID else { return }
        let cleaned = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        if !cleaned.isEmpty {
            transition(.segmentTranscribed(cleaned))
        }
        scheduleFinish(sessionID: sessionID)
    }

    private func failTranscription(sessionID: UUID) {
        transcriptionTask = nil
        guard activeSessionID == sessionID else { return }
        activeSessionID = nil
        isFinishing = false
        recorder.reset()
        stopCapture(discardPending: true)
        transition(.failed("Local voice input is preparing"))
    }

    private func scheduleFinish(sessionID: UUID) {
        Task { @MainActor [weak self] in
            await Task.yield()
            guard self?.activeSessionID == sessionID else { return }
            self?.finishIfReady()
        }
    }

    private func finishIfReady() {
        guard isFinishing, transcriptionTask == nil else { return }
        activeSessionID = nil
        isFinishing = false
        recorder.reset()
        transition(.sessionFinished)
    }

    private func handleInputDeviceLoss(sessionID: UUID) {
        guard activeSessionID == sessionID else { return }
        activeSessionID = nil
        isFinishing = false
        recorder.reset()
        stopCapture(discardPending: true)
        transition(.inputDeviceLost)
    }

    private func stopCapture(discardPending: Bool) {
        if let audioConfigurationObserver {
            NotificationCenter.default.removeObserver(audioConfigurationObserver)
            self.audioConfigurationObserver = nil
        }
        if let engine = audioEngine {
            if hasInputTap {
                engine.inputNode.removeTap(onBus: 0)
                hasInputTap = false
            }
            if engine.isRunning {
                engine.stop()
            }
        }
        audioEngine = nil
        pcmConverter = nil
        pcmFormat = nil
        if discardPending {
            transcriptionTask?.cancel()
            transcriptionTask = nil
        }
    }

    private func transition(_ event: SpeechRecognitionEvent) {
        state = stateMachine.apply(event)
        onStateChange?(state)
    }

    private static func convertToPCM16(
        _ buffer: AVAudioPCMBuffer,
        converter: AVAudioConverter,
        outputFormat: AVAudioFormat
    ) -> Data? {
        let ratio = outputFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(max(1, Int(Double(buffer.frameLength) * ratio) + 1))
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            return nil
        }
        var error: NSError?
        var consumedInput = false
        let status = converter.convert(to: output, error: &error) { _, statusPointer in
            if consumedInput {
                statusPointer.pointee = .noDataNow
                return nil
            }
            consumedInput = true
            statusPointer.pointee = .haveData
            return buffer
        }
        guard status != .error, error == nil, output.frameLength > 0,
              let channelData = output.int16ChannelData
        else { return nil }
        return Data(
            bytes: channelData.pointee,
            count: Int(output.frameLength) * MemoryLayout<Int16>.size
        )
    }
}

private let VOICE_SAMPLE_RATE_HZ = 16_000
