import asyncio
import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from across_agents_assistant import api_server
from across_agents_assistant.local_voice_transcription import (
    LocalVoiceTranscriber,
    MAX_RECORDING_SECONDS,
    SAMPLE_RATE_HZ,
    SpeechChunk,
    normalize_segment_transcript,
)


def _pcm(samples: int = 1_600, value: int = 4_000) -> bytes:
    return int(value).to_bytes(2, byteorder="little", signed=True) * samples


def test_local_voice_transcriber_loads_once_and_keeps_pcm_in_memory(tmp_path):
    factory_calls = []

    class FakeModel:
        def transcribe(self, samples, **kwargs):
            assert samples.dtype.name == "float32"
            assert samples.shape == (1_600,)
            assert kwargs["language"] is None
            assert kwargs["task"] == "transcribe"
            assert kwargs["vad_filter"] is False
            assert kwargs["condition_on_previous_text"] is False
            return [SimpleNamespace(text=" Local voice ")], SimpleNamespace(language="en")

    def factory(*args, **kwargs):
        factory_calls.append((args, kwargs))
        return FakeModel()

    transcriber = LocalVoiceTranscriber(
        cache_dir=tmp_path,
        model_factory=factory,
        speech_chunker=lambda samples: [SpeechChunk(0, len(samples))],
    )
    first = transcriber.transcribe_pcm16(
        _pcm(), sample_rate_hz=SAMPLE_RATE_HZ, locale_identifier="zh-Hans"
    )
    second = transcriber.transcribe_pcm16(
        _pcm(), sample_rate_hz=SAMPLE_RATE_HZ, locale_identifier="zh-CN"
    )

    assert first.text == "Local voice."
    assert second.language == "en"
    assert len(factory_calls) == 1
    assert factory_calls[0][1]["download_root"] == str(tmp_path)


def test_finished_recording_uses_pauses_for_punctuation_without_partial_results(tmp_path):
    responses = iter(
        [
            ("first thought", "en"),
            ("continues here", "en"),
            ("final sentence", "en"),
        ]
    )

    class FakeModel:
        def transcribe(self, samples, **kwargs):
            text, language = next(responses)
            return [SimpleNamespace(text=text)], SimpleNamespace(language=language)

    chunks = [
        SpeechChunk(0, 8_000),
        SpeechChunk(18_000, 26_000),  # short pause -> comma
        SpeechChunk(48_000, 56_000),  # long pause -> sentence
    ]
    transcriber = LocalVoiceTranscriber(
        cache_dir=tmp_path,
        model_factory=lambda *_args, **_kwargs: FakeModel(),
        speech_chunker=lambda _samples: chunks,
    )

    result = transcriber.transcribe_pcm16(
        _pcm(samples=56_000),
        sample_rate_hz=SAMPLE_RATE_HZ,
        locale_identifier="zh-Hans",
    )

    assert result.text == "first thought, continues here. Final sentence."
    assert result.language == "en"


def test_finished_chinese_recording_uses_pause_punctuation_without_newlines(tmp_path):
    responses = iter([("第一句", "zh"), ("继续说明", "zh")])

    class FakeModel:
        def transcribe(self, samples, **kwargs):
            text, language = next(responses)
            return [SimpleNamespace(text=text)], SimpleNamespace(language=language)

    transcriber = LocalVoiceTranscriber(
        cache_dir=tmp_path,
        model_factory=lambda *_args, **_kwargs: FakeModel(),
        speech_chunker=lambda _samples: [
            SpeechChunk(0, 8_000),
            SpeechChunk(20_000, 28_000),
        ],
    )
    result = transcriber.transcribe_pcm16(
        _pcm(samples=28_000),
        sample_rate_hz=SAMPLE_RATE_HZ,
        locale_identifier="zh-Hans",
    )

    assert result.text == "第一句，继续说明。"
    assert "\n" not in result.text


def test_segment_transcripts_gain_natural_fallback_punctuation_without_duplication():
    assert MAX_RECORDING_SECONDS == 180
    assert normalize_segment_transcript("你好", "zh") == "你好。"
    assert normalize_segment_transcript("你好！", "zh") == "你好！"
    assert normalize_segment_transcript("Hello there", "en") == "Hello there."
    assert normalize_segment_transcript('"Already done."', "en") == '"Already done."'
    assert normalize_segment_transcript('"Almost done,"', "en") == '"Almost done."'
    assert normalize_segment_transcript("   ", "en") == ""


def test_voice_endpoint_decodes_only_valid_bounded_pcm(monkeypatch):
    seen = {}

    def fake_transcribe(pcm16le, *, sample_rate_hz, locale_identifier):
        seen.update(pcm16le=pcm16le, sample_rate_hz=sample_rate_hz, locale_identifier=locale_identifier)
        return SimpleNamespace(text="editable draft")

    monkeypatch.setattr(api_server, "transcribe_voice_pcm16", fake_transcribe)
    request = api_server.VoiceTranscriptionRequest(
        pcm16le_base64=base64.b64encode(_pcm()).decode("ascii"),
        sample_rate_hz=SAMPLE_RATE_HZ,
        locale_identifier="en-US",
    )

    response = asyncio.run(api_server.transcribe_voice_input(request))

    assert response.transcript == "editable draft"
    assert seen == {
        "pcm16le": _pcm(),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "locale_identifier": "en-US",
    }


def test_voice_endpoint_rejects_invalid_base64_without_calling_engine(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "transcribe_voice_pcm16",
        lambda *_args, **_kwargs: pytest.fail("engine must not receive invalid audio"),
    )
    request = api_server.VoiceTranscriptionRequest(
        pcm16le_base64="not base64!",
        sample_rate_hz=SAMPLE_RATE_HZ,
        locale_identifier="en-US",
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(api_server.transcribe_voice_input(request))

    assert excinfo.value.status_code == 400
