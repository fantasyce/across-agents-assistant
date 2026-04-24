import Vision

if #available(macOS 11.0, *) {
    do {
        let langs = try VNRecognizeTextRequest.supportedRecognitionLanguages(for: .accurate, revision: VNRecognizeTextRequestRevision2)
        print("Supported langs revision 2: \(langs)")
        
        let langs1 = try VNRecognizeTextRequest.supportedRecognitionLanguages(for: .accurate, revision: VNRecognizeTextRequestRevision1)
        print("Supported langs revision 1: \(langs1)")
    } catch {
        print("Error: \(error)")
    }
}
