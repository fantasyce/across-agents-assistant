import AVFoundation

class TTSEngine: NSObject, AVSpeechSynthesizerDelegate {
    static let shared = TTSEngine()
    
    private let synthesizer = AVSpeechSynthesizer()
    private var preferredVoice: AVSpeechSynthesisVoice?
    
    override init() {
        super.init()
        synthesizer.delegate = self
        
        // Try to find a high quality Chinese voice, prefer TingTing or Siri
        let voices = AVSpeechSynthesisVoice.speechVoices()
        preferredVoice = voices.first(where: { $0.language == "zh-CN" && $0.quality == .enhanced }) 
            ?? voices.first(where: { $0.language == "zh-CN" })
    }
    
    func speak(_ text: String) {
        // Stop currently playing speech
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = preferredVoice
        
        // Make it sound more natural
        utterance.rate = 0.52 
        utterance.pitchMultiplier = 1.0
        utterance.volume = 1.0
        
        // Slight pause before punctuation for better phrasing
        utterance.preUtteranceDelay = 0.05
        
        synthesizer.speak(utterance)
    }
    
    func stop() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
    }
}
