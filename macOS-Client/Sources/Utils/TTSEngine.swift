import AVFoundation
import AppKit

class TTSEngine: NSObject, AVSpeechSynthesizerDelegate, @unchecked Sendable {
    static let shared = TTSEngine()
    
    private let synthesizer = AVSpeechSynthesizer()
    
    // We no longer need to cache a preferredVoice, we will fetch the system default on the fly.
    
    var hasHighQualityVoice: Bool {
        // Just check if the current system default is premium/enhanced
        let systemVoiceId = NSSpeechSynthesizer.defaultVoice.rawValue
        let voice = AVSpeechSynthesisVoice(identifier: systemVoiceId)
        return voice?.quality == .premium || voice?.quality == .enhanced
    }
    
    private override init() {
        super.init()
        synthesizer.delegate = self
    }
    
    func speak(_ text: String) {
        // Stop immediately to prevent overlapping/echoing ("重音")
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        
        let utterance = AVSpeechUtterance(string: text)
        
        // --- THE MAGIC: Read the user's actual selection from macOS System Settings ---
        let systemVoiceId = NSSpeechSynthesizer.defaultVoice.rawValue
        if let userSelectedVoice = AVSpeechSynthesisVoice(identifier: systemVoiceId) {
            utterance.voice = userSelectedVoice
            print("Using user's exact macOS System Voice: \(userSelectedVoice.name) (Quality: \(userSelectedVoice.quality.rawValue))")
        } else {
            // Absolute fallback if the system API fails
            utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
            print("Fallback to generic zh-CN voice")
        }
        
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
