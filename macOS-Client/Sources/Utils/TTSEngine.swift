import AVFoundation
import AppKit

class TTSEngine: NSObject, AVSpeechSynthesizerDelegate, @unchecked Sendable {
    static let shared = TTSEngine()

    private let synthesizer = AVSpeechSynthesizer()

    // We no longer need to cache a preferredVoice, we will fetch the system default on the fly.

    var hasHighQualityVoice: Bool {
        let voice = Self.voiceForSpeech()
        return voice?.quality == .premium || voice?.quality == .enhanced
    }

    private override init() {
        super.init()
        synthesizer.delegate = self
    }

    func speak(
        _ text: String,
        voiceSource: AppVoiceSource = .followSystem,
        chosenVoiceIdentifier: String? = nil,
        fallbackLanguage: String = Locale.preferredLanguages.first ?? "zh-CN",
        rate: Double = 0.48,
        volume: Double = 1.0
    ) {
        // Stop immediately to prevent overlapping or doubled speech.
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }

        let utterance = AVSpeechUtterance(string: text)

        if let preferredVoice = Self.voiceForSpeech(
            voiceSource: voiceSource,
            chosenVoiceIdentifier: chosenVoiceIdentifier,
            fallbackLanguage: fallbackLanguage
        ) {
            utterance.voice = preferredVoice
            print("Using AVFoundation voice: \(preferredVoice.name) (Quality: \(preferredVoice.quality.rawValue))")
        } else {
            utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
            print("Fallback to generic zh-CN voice")
        }

        // Tune parameters to make the voice sound less stiff.
        utterance.rate = Float(rate) // Slightly slower than default 0.5 for better articulation
        utterance.pitchMultiplier = 1.05 // Slight pitch variation for more natural tone
        utterance.volume = Float(volume)

        // Add natural breathing pauses
        utterance.preUtteranceDelay = 0.05
        utterance.postUtteranceDelay = 0.1

        synthesizer.speak(utterance)
    }

    static func voiceForSpeech(
        voiceSource: AppVoiceSource = .followSystem,
        systemVoiceIdentifier: String? = currentSystemVoiceIdentifier(),
        chosenVoiceIdentifier: String? = nil,
        fallbackLanguage: String = Locale.preferredLanguages.first ?? "zh-CN"
    ) -> AVSpeechSynthesisVoice? {
        switch voiceSource {
        case .chosenVoice:
            if let chosenVoiceIdentifier,
               let chosenVoice = AVSpeechSynthesisVoice(identifier: chosenVoiceIdentifier) {
                return chosenVoice
            }
            return bestInstalledVoice(language: fallbackLanguage)
        case .bestInstalled:
            return bestInstalledVoice(language: fallbackLanguage)
        case .followSystem:
            if let systemVoiceIdentifier,
               let userSelectedVoice = AVSpeechSynthesisVoice(identifier: systemVoiceIdentifier) {
                return userSelectedVoice
            }
            return bestInstalledVoice(language: fallbackLanguage)
        }
    }

    private static func bestInstalledVoice(language: String) -> AVSpeechSynthesisVoice? {
        let normalizedLanguage = normalizedLanguagePrefix(language)
        let matchingVoices = AVSpeechSynthesisVoice.speechVoices().filter {
            $0.language.lowercased().hasPrefix(normalizedLanguage)
        }

        return matchingVoices.sorted { lhs, rhs in
            if lhs.quality.rawValue != rhs.quality.rawValue {
                return lhs.quality.rawValue > rhs.quality.rawValue
            }
            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }.first
            ?? AVSpeechSynthesisVoice(language: language)
            ?? AVSpeechSynthesisVoice(language: "zh-CN")
            ?? AVSpeechSynthesisVoice.speechVoices().first
    }

    private static func normalizedLanguagePrefix(_ language: String) -> String {
        let lowered = language.lowercased()
        if lowered.hasPrefix("zh") { return "zh" }
        return String(lowered.prefix(2))
    }

    private static func currentSystemVoiceIdentifier() -> String? {
        let selector = NSSelectorFromString("defaultVoice")
        guard let speechSynthesizerClass = NSClassFromString("NSSpeechSynthesizer") as AnyObject?,
              speechSynthesizerClass.responds(to: selector),
              let unmanaged = speechSynthesizerClass.perform(selector),
              let voiceIdentifier = unmanaged.takeUnretainedValue() as? String
        else {
            return nil
        }

        return voiceIdentifier
    }

    func stop() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
    }
}
