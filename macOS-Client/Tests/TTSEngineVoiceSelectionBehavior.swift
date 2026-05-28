import AVFoundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testSelectsExactUserSystemVoiceIdentifierWhenAvailable() {
    guard let installedVoice = AVSpeechSynthesisVoice.speechVoices().first else {
        print("Skipping TTSEngine voice selection test: no speech voices are installed")
        return
    }

    guard let selected = TTSEngine.voiceForSpeech(
        systemVoiceIdentifier: installedVoice.identifier,
        fallbackLanguage: installedVoice.language
    ) else {
        fatalError("TTSEngine should select an available system voice")
    }

    assert(
        selected.identifier == installedVoice.identifier,
        "TTSEngine should use the exact user-selected system voice identifier"
    )
}

func testChosenVoiceFallsBackToBestInstalledWhenUnavailable() {
    guard let installedVoice = AVSpeechSynthesisVoice.speechVoices().first else {
        print("Skipping TTSEngine fallback test: no speech voices are installed")
        return
    }

    guard let selected = TTSEngine.voiceForSpeech(
        voiceSource: .chosenVoice,
        systemVoiceIdentifier: nil,
        chosenVoiceIdentifier: "missing.voice.identifier",
        fallbackLanguage: installedVoice.language
    ) else {
        fatalError("TTSEngine should fall back to an installed voice")
    }

    assert(
        selected.language == installedVoice.language,
        "TTSEngine should fall back to the requested language when a chosen voice is missing"
    )
}

@main
struct TTSEngineVoiceSelectionBehavior {
    static func main() {
        testSelectsExactUserSystemVoiceIdentifierWhenAvailable()
        testChosenVoiceFallsBackToBestInstalledWhenUnavailable()
        print("TTSEngineVoiceSelectionBehavior passed")
    }
}
