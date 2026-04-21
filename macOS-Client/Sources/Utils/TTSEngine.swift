import AVFoundation

class TTSEngine: NSObject, AVSpeechSynthesizerDelegate, @unchecked Sendable {
    static let shared = TTSEngine()
    
    private let synthesizer = AVSpeechSynthesizer()
    private var preferredVoice: AVSpeechSynthesisVoice?
    
    var hasHighQualityVoice: Bool {
        return preferredVoice?.quality == .premium || preferredVoice?.quality == .enhanced
    }
    
    private override init() {
        super.init()
        synthesizer.delegate = self
        
        setupVoice()
        
        // Listen for system voice changes (e.g., user downloaded a new voice in System Settings)
        if #available(macOS 14.0, *) {
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(voicesDidChange),
                name: AVSpeechSynthesizer.availableVoicesDidChangeNotification,
                object: nil
            )
        }
    }
    
    @objc private func voicesDidChange() {
        print("Detected system voice changes. Reloading voices...")
        setupVoice()
    }
    
    private func setupVoice() {
        // Try to find a high quality Chinese voice
        let voices = AVSpeechSynthesisVoice.speechVoices()
        let chineseVoices = voices.filter { $0.language.starts(with: "zh") }
        
        // Prefer Premium > Enhanced > Standard
        preferredVoice = chineseVoices.first(where: { $0.quality == .premium })
            ?? chineseVoices.first(where: { $0.quality == .enhanced })
            ?? chineseVoices.first
            
        print("Selected voice: \(preferredVoice?.name ?? "None") (Quality: \(preferredVoice?.quality.rawValue ?? -1))")
    }
    
    func speak(_ text: String) {
        // Stop immediately to prevent overlapping/echoing ("重音")
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = preferredVoice
        
        // Tune parameters to make it sound less robotic ("生硬")
        utterance.rate = 0.48 // Slightly slower than default 0.5 for better articulation
        utterance.pitchMultiplier = 1.05 // Slight pitch variation for more natural tone
        utterance.volume = 1.0
        
        // Add natural breathing pauses
        utterance.preUtteranceDelay = 0.05
        utterance.postUtteranceDelay = 0.1
        
        synthesizer.speak(utterance)
    }
    
    func stop() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
    }
}
