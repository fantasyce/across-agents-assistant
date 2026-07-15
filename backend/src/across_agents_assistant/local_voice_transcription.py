"""Private local speech-to-text used by the macOS voice-input control.

Audio is captured by the signed Swift host after its microphone permission has
been granted.  This module receives one explicitly finished in-memory PCM
recording through the app's Unix socket, transcribes it locally, and returns
text.  It never writes microphone samples or transcripts to disk.
"""

from __future__ import annotations

import os
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .paths import component_cache_home


VOICE_MODEL_NAME = "small"
SAMPLE_RATE_HZ = 16_000
MAX_RECORDING_SECONDS = 180
MAX_PCM_BYTES = SAMPLE_RATE_HZ * 2 * MAX_RECORDING_SECONDS
MIN_PUNCTUATION_PAUSE_MS = 650
SENTENCE_PAUSE_SECONDS = 1.0
MAX_TRANSCRIPTION_CHUNKS = 48


class LocalVoiceTranscriptionError(RuntimeError):
    """A safe, user-actionable failure from the local ASR boundary."""


@dataclass(frozen=True)
class LocalVoiceTranscript:
    text: str
    language: str


@dataclass(frozen=True)
class SpeechChunk:
    start_sample: int
    end_sample: int


def voice_model_cache_dir() -> Path:
    """Keep downloaded model data under the product runtime root."""

    path = component_cache_home() / "voice-models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def language_for_locale(locale_identifier: str) -> str:
    normalized = (locale_identifier or "").replace("_", "-").lower()
    return "zh" if normalized.startswith("zh") else "en"


_TRAILING_SENTENCE_PUNCTUATION = frozenset(".?!。！？…")
_TRAILING_CLAUSE_PUNCTUATION = frozenset(",;:，；：、")
_CLOSING_QUOTES = frozenset("'\"’”）)]】》」』")


def normalize_segment_transcript(text: str, language: str) -> str:
    """Return one readable finished-recording transcript without inventing words."""

    cleaned = text.strip()
    if not cleaned:
        return ""
    punctuation_probe = cleaned.rstrip("".join(_CLOSING_QUOTES))
    closing_count = len(cleaned) - len(punctuation_probe)
    closers = cleaned[-closing_count:] if closing_count else ""
    if punctuation_probe and punctuation_probe[-1] in _TRAILING_SENTENCE_PUNCTUATION:
        return cleaned
    punctuation = "。" if language.lower().startswith("zh") else "."
    if punctuation_probe and punctuation_probe[-1] in _TRAILING_CLAUSE_PUNCTUATION:
        return punctuation_probe[:-1] + punctuation + closers
    return punctuation_probe + punctuation + closers


def detect_speech_chunks(samples: Any) -> list[SpeechChunk]:
    """Find punctuation-worthy utterances after the user finishes recording."""

    from faster_whisper.vad import VadOptions, get_speech_timestamps

    timestamps = get_speech_timestamps(
        samples,
        VadOptions(
            min_speech_duration_ms=120,
            min_silence_duration_ms=MIN_PUNCTUATION_PAUSE_MS,
            speech_pad_ms=120,
        ),
        sampling_rate=SAMPLE_RATE_HZ,
    )
    chunks = [
        SpeechChunk(
            start_sample=max(0, int(timestamp["start"])),
            end_sample=min(len(samples), int(timestamp["end"])),
        )
        for timestamp in timestamps
        if int(timestamp["end"]) > int(timestamp["start"])
    ]
    if len(chunks) <= MAX_TRANSCRIPTION_CHUNKS:
        return chunks

    # Bound inference work for a pathological three-minute recording while
    # preserving chronological content. Typical speech never reaches this.
    group_size = math.ceil(len(chunks) / MAX_TRANSCRIPTION_CHUNKS)
    return [
        SpeechChunk(group[0].start_sample, group[-1].end_sample)
        for offset in range(0, len(chunks), group_size)
        if (group := chunks[offset : offset + group_size])
    ]


def _punctuation_probe(text: str) -> str:
    return text.rstrip("".join(_CLOSING_QUOTES))


def _replace_trailing_period(text: str, replacement: str) -> str:
    closing_count = len(text) - len(_punctuation_probe(text))
    core = text[:-closing_count] if closing_count else text
    closers = text[-closing_count:] if closing_count else ""
    if core.endswith((".", "。")):
        core = core[:-1] + replacement
    return core + closers


def _capitalize_initial_latin(text: str) -> str:
    for index, character in enumerate(text):
        if character.isalpha():
            if character.isascii():
                return text[:index] + character.upper() + text[index + 1 :]
            return text
    return text


def _is_cjk(character: str) -> bool:
    return any(
        "\u3400" <= scalar <= "\u4dbf"
        or "\u4e00" <= scalar <= "\u9fff"
        or "\U00020000" <= scalar <= "\U0002fa1f"
        for scalar in character
    )


def _join_transcribed_chunks(
    chunks: list[tuple[SpeechChunk, str, str]],
) -> str:
    """Restore punctuation from pauses without publishing partial drafts."""

    rendered: list[str] = []
    for index, (chunk, raw_text, language) in enumerate(chunks):
        text = raw_text.strip()
        if not text:
            continue
        is_last = index == len(chunks) - 1
        if is_last:
            text = normalize_segment_transcript(text, language)
        else:
            next_chunk = chunks[index + 1][0]
            pause_seconds = max(
                0.0,
                (next_chunk.start_sample - chunk.end_sample) / SAMPLE_RATE_HZ,
            )
            sentence_break = pause_seconds >= SENTENCE_PAUSE_SECONDS
            probe = _punctuation_probe(text)
            if probe and probe[-1] in {".", "。"} and not sentence_break:
                text = _replace_trailing_period(
                    text,
                    "，" if language.startswith("zh") else ",",
                )
            elif probe and probe[-1] not in (
                _TRAILING_SENTENCE_PUNCTUATION | _TRAILING_CLAUSE_PUNCTUATION
            ):
                if sentence_break:
                    text += "。" if language.startswith("zh") else "."
                else:
                    text += "，" if language.startswith("zh") else ","

        if rendered:
            previous_probe = _punctuation_probe(rendered[-1])
            previous_ends_sentence = bool(
                previous_probe
                and previous_probe[-1] in _TRAILING_SENTENCE_PUNCTUATION
            )
            if previous_ends_sentence:
                text = _capitalize_initial_latin(text)

            previous_character = next(
                (
                    character
                    for character in reversed(previous_probe)
                    if character.isalnum()
                ),
                "",
            )
            next_character = next(
                (character for character in text if character.isalnum()),
                "",
            )
            separator = ""
            if not (
                previous_character
                and next_character
                and _is_cjk(previous_character)
                and _is_cjk(next_character)
            ):
                separator = " "
            rendered.append(separator + text)
        else:
            rendered.append(text)
    return "".join(rendered)


class LocalVoiceTranscriber:
    """Lazy Faster-Whisper host for one explicitly finished recording."""

    def __init__(
        self,
        *,
        model_name: str = VOICE_MODEL_NAME,
        cache_dir: Path | None = None,
        model_factory: Callable[..., Any] | None = None,
        speech_chunker: Callable[[Any], list[SpeechChunk]] | None = None,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir or voice_model_cache_dir()
        self._model_factory = model_factory
        self._speech_chunker = speech_chunker or detect_speech_chunks
        self._model: Any | None = None
        self._lock = threading.RLock()

    def transcribe_pcm16(
        self,
        pcm16le: bytes,
        *,
        sample_rate_hz: int,
        locale_identifier: str,
    ) -> LocalVoiceTranscript:
        if sample_rate_hz != SAMPLE_RATE_HZ:
            raise LocalVoiceTranscriptionError("unsupported_sample_rate")
        if not pcm16le or len(pcm16le) % 2 != 0:
            raise LocalVoiceTranscriptionError("invalid_pcm")
        if len(pcm16le) > MAX_PCM_BYTES:
            raise LocalVoiceTranscriptionError("segment_too_large")

        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - build check covers this path
            raise LocalVoiceTranscriptionError("local_engine_unavailable") from exc

        samples = np.frombuffer(pcm16le, dtype=np.dtype("<i2")).astype(np.float32)
        samples /= 32768.0
        fallback_language = language_for_locale(locale_identifier)

        # CTranslate2 model objects are safe to retain, but serialized inference
        # prevents overlapping recordings from changing transcript order.
        with self._lock:
            model = self._load_model_locked()
            try:
                speech_chunks = self._speech_chunker(samples)
                recognized_chunks: list[tuple[SpeechChunk, str, str]] = []
                language_weights: dict[str, int] = {}
                for chunk in speech_chunks:
                    segments, info = model.transcribe(
                        samples[chunk.start_sample : chunk.end_sample],
                        # A Chinese UI must not force spoken English into Chinese.
                        # Detect each completed phrase and explicitly transcribe
                        # rather than translate it.
                        language=None,
                        task="transcribe",
                        beam_size=5,
                        # VAD already ran over the finished recording so the
                        # model can retain phrase boundaries as punctuation.
                        vad_filter=False,
                        without_timestamps=True,
                        condition_on_previous_text=False,
                    )
                    detected = str(
                        getattr(info, "language", "") or fallback_language
                    ).lower()
                    raw_text = "".join(str(segment.text) for segment in segments).strip()
                    if not raw_text:
                        continue
                    recognized_chunks.append((chunk, raw_text, detected))
                    language_weights[detected] = language_weights.get(detected, 0) + (
                        chunk.end_sample - chunk.start_sample
                    )
                detected_language = max(
                    language_weights,
                    key=language_weights.get,
                    default=fallback_language,
                )
                text = _join_transcribed_chunks(recognized_chunks)
            except Exception as exc:
                raise LocalVoiceTranscriptionError("transcription_failed") from exc
        return LocalVoiceTranscript(text=text, language=detected_language)

    def _load_model_locked(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            factory = self._model_factory
            if factory is None:
                from faster_whisper import WhisperModel

                factory = WhisperModel
            self._model = factory(
                self._model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, min(4, os.cpu_count() or 1)),
                download_root=str(self._cache_dir),
            )
            return self._model
        except Exception as exc:
            raise LocalVoiceTranscriptionError("local_model_unavailable") from exc


_shared_transcriber: LocalVoiceTranscriber | None = None
_shared_transcriber_lock = threading.Lock()


def transcribe_voice_pcm16(
    pcm16le: bytes,
    *,
    sample_rate_hz: int,
    locale_identifier: str,
) -> LocalVoiceTranscript:
    global _shared_transcriber
    if _shared_transcriber is None:
        with _shared_transcriber_lock:
            if _shared_transcriber is None:
                _shared_transcriber = LocalVoiceTranscriber()
    return _shared_transcriber.transcribe_pcm16(
        pcm16le,
        sample_rate_hz=sample_rate_hz,
        locale_identifier=locale_identifier,
    )
