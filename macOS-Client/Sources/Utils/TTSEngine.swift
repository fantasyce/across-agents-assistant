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
        let voices = AVSpeechSynthesisVoice.speechVoices()
        let chineseVoices = voices.filter { $0.language.starts(with: "zh") }
        
        // Define a flexible voice selection hierarchy
        // Priority 1: Specific high-quality voices we love (Lilian, Tingting)
        let preferredNames = ["Lilian", "Tingting", "Lili", "Siri"]
        
        for name in preferredNames {
            if let matchedVoice = chineseVoices.filter({ $0.name.contains(name) })
                .max(by: { $0.quality.rawValue < $1.quality.rawValue }) {
                
                // Only accept it if it's at least Enhanced quality
                if matchedVoice.quality == .premium || matchedVoice.quality == .enhanced {
                    preferredVoice = matchedVoice
                    print("Selected preferred voice: \(matchedVoice.name) (Quality: \(matchedVoice.quality.rawValue))")
                    return
                }
            }
        }
        
        // Priority 2: Any Premium Chinese voice
        if let premiumVoice = chineseVoices.first(where: { $0.quality == .premium }) {
            preferredVoice = premiumVoice
            print("Selected fallback Premium voice: \(premiumVoice.name)")
            return
        }
        
        // Priority 3: Any Enhanced Chinese voice
        if let enhancedVoice = chineseVoices.first(where: { $0.quality == .enhanced }) {
            preferredVoice = enhancedVoice
            print("Selected fallback Enhanced voice: \(enhancedVoice.name)")
            return
        }
        
        // Priority 4: The absolute default basic voice (Robotic fallback)
        preferredVoice = chineseVoices.first
        print("Selected basic fallback voice: \(preferredVoice?.name ?? "None")")
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
