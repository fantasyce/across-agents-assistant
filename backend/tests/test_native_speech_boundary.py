from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_voice_input_uses_only_the_microphone_and_a_private_local_engine():
    legacy_speech_dir = ROOT / "backend/src/across_agents_assistant/speech"
    assert not list(legacy_speech_dir.glob("*.py"))
    assert not (ROOT / "backend/src/across_agents_assistant/wakeword.py").exists()

    service = (
        ROOT / "macOS-Client/Sources/Utils/SpeechRecognitionService.swift"
    ).read_text(encoding="utf-8")
    app_builder = (ROOT / "build_app.sh").read_text(encoding="utf-8")
    requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8").lower()
    behavior_checks = (ROOT / "scripts/run_swift_behavior_checks.sh").read_text(encoding="utf-8")

    assert "AVAudioEngine" in service
    assert "AVCaptureDevice.requestAccess(for: .audio)" in service
    assert "SpeechSessionRecorder" in service
    assert "trailingSilenceSamples" not in service
    assert "finishRecording(recorder.finish()" in service
    assert "segmentTranscript" in service
    assert "/api/voice/transcribe" in service
    assert "SFSpeechRecognizer" not in service
    assert "import Speech" not in service
    assert "NSSpeechRecognitionUsageDescription" not in app_builder
    assert "-framework Speech" not in behavior_checks
    assert "NSMicrophoneUsageDescription" in app_builder
    assert "faster-whisper" in requirements
    assert "--collect-all faster_whisper" in app_builder


def test_voice_runtime_keeps_audio_ephemeral_and_drops_old_microphone_capture_stack():
    local_engine = (
        ROOT / "backend/src/across_agents_assistant/local_voice_transcription.py"
    ).read_text(encoding="utf-8").lower()
    production_manifests = [
        ROOT / "backend/requirements.txt",
        ROOT / "backend/requirements_no_pyobjc.txt",
        ROOT / "backend/requirements_filtered.txt",
        ROOT / "backend/build.py",
        ROOT / "legal/THIRD_PARTY_NOTICES.md",
    ]
    for path in production_manifests:
        text = path.read_text(encoding="utf-8").lower()
        assert "sounddevice" not in text, path
        assert "webrtcvad" not in text, path

    normalized_engine = " ".join(local_engine.split())
    assert "never writes microphone samples" in normalized_engine
    assert "open(" not in local_engine
    assert "write_bytes" not in local_engine
