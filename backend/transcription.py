from __future__ import annotations

import json
import threading
import wave
from pathlib import Path
from typing import Any, Callable, Optional

from vosk import KaldiRecognizer, Model, SetLogLevel

import config

\
SetLogLevel(-1)

_MODEL_LOCK = threading.Lock()
_CACHED_MODEL: Optional[Model] = None
_CACHED_MODEL_PATH: Optional[Path] = None


class TranscriptionError(RuntimeError):
    pass


def get_vosk_model(model_path: Optional[Path] = None) -> Model:
    global _CACHED_MODEL, _CACHED_MODEL_PATH

    target_path = Path(model_path or config.VOSK_MODEL_PATH)
    if not target_path.exists() or not target_path.is_dir():
        raise TranscriptionError(
            f"Vosk English model not found at '{target_path}'. "
            "Download 'vosk-model-small-en-us-0.15' and place it in models/vosk-model-small-en-us/."
        )

    with _MODEL_LOCK:
        if _CACHED_MODEL is None or _CACHED_MODEL_PATH != target_path:
            _CACHED_MODEL = Model(str(target_path))
            _CACHED_MODEL_PATH = target_path
        return _CACHED_MODEL


def is_vosk_model_ready(model_path: Optional[Path] = None) -> bool:
    target_path = Path(model_path or config.VOSK_MODEL_PATH)
    return target_path.is_dir() and (target_path / "conf").is_dir()


def group_words_into_sentences(
    word_segments: list[dict[str, Any]],
    pause_threshold: float = 0.75,
    max_words_per_sentence: int = 12,
) -> list[dict[str, Any]]:
    if not word_segments:
        return []

    sentences: list[dict[str, Any]] = []
    current_words: list[dict[str, Any]] = []

    for word in word_segments:
        if not current_words:
            current_words.append(word)
            continue

        prev = current_words[-1]
        gap = float(word["start"]) - float(prev["end"])
        if gap >= pause_threshold or len(current_words) >= max_words_per_sentence:
            sentences.append(_finalize_sentence(len(sentences) + 1, current_words))
            current_words = [word]
        else:
            current_words.append(word)

    if current_words:
        sentences.append(_finalize_sentence(len(sentences) + 1, current_words))

    return sentences


def _finalize_sentence(index: int, words: list[dict[str, Any]]) -> dict[str, Any]:
    raw_text = " ".join(w["text"] for w in words).strip()
    display_text = raw_text[:1].upper() + raw_text[1:] if raw_text else ""
    return {
        "id": f"seg_{index:04d}",
        "start": round(float(words[0]["start"]), 3),
        "end": round(float(words[-1]["end"]), 3),
        "text": display_text,
        "words": words,
        "asl_status": "pending_phase_3",
    }


def _collect_result_words(payload: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for item in payload.get("result", []) or []:
        text = str(item.get("word") or "").strip()
        if not text:
            continue
        words.append(
            {
                "start": round(float(item.get("start", 0.0)), 3),
                "end": round(float(item.get("end", 0.0)), 3),
                "text": text,
                "confidence": round(float(item.get("conf", 1.0)), 3),
            }
        )
    return words


def transcribe_wav(
    wav_path: Path,
    output_json_path: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    model_path: Optional[Path] = None,
) -> dict[str, Any]:
    if not wav_path.exists():
        raise TranscriptionError(f"Extracted WAV audio file not found: {wav_path}")

    model = get_vosk_model(model_path=model_path)

    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            total_frames = wf.getnframes()

            if channels != 1 or sample_width != 2 or sample_rate != config.VOSK_SAMPLE_RATE:
                raise TranscriptionError(
                    f"Unsupported WAV format (channels={channels}, width={sample_width}, rate={sample_rate}). "
                    "Expected mono 16-bit PCM at 16000 Hz."
                )

            recognizer = KaldiRecognizer(model, sample_rate)
            recognizer.SetWords(True)

            word_segments: list[dict[str, Any]] = []
            utterance_texts: list[str] = []
            processed_frames = 0
            last_reported_pct = -1

            while True:
                data = wf.readframes(config.AUDIO_CHUNK_FRAMES)
                if len(data) == 0:
                    break

                processed_frames += len(data) // (channels * sample_width)

                if recognizer.AcceptWaveform(data):
                    res = json.loads(recognizer.Result())
                    text_chunk = str(res.get("text") or "").strip()
                    if text_chunk:
                        utterance_texts.append(text_chunk)
                    word_segments.extend(_collect_result_words(res))

                if progress_callback and total_frames > 0:
                    pct = min(99, int((processed_frames / total_frames) * 100))
                    if pct != last_reported_pct:
                        last_reported_pct = pct
                        partial = json.loads(recognizer.PartialResult()).get("partial", "")
                        preview = " ".join(utterance_texts + ([partial] if partial else [])).strip()
                        progress_callback(pct, preview)

            final_res = json.loads(recognizer.FinalResult())
            final_text = str(final_res.get("text") or "").strip()
            if final_text:
                utterance_texts.append(final_text)
            word_segments.extend(_collect_result_words(final_res))

            audio_duration = round(total_frames / float(sample_rate), 3) if total_frames > 0 else 0.0
    except wave.Error as exc:
        raise TranscriptionError(f"Could not read WAV audio stream: {exc}") from exc

    full_text = " ".join(utterance_texts).strip()
    sentences = group_words_into_sentences(word_segments)

    \
    if full_text and not word_segments:
        sentences = [
            {
                "id": "seg_0001",
                "start": 0.0,
                "end": audio_duration,
                "text": full_text[:1].upper() + full_text[1:],
                "words": [],
                "asl_status": "pending_phase_3",
            }
        ]

    transcript_payload: dict[str, Any] = {
        "text": full_text,
        "duration_seconds": audio_duration,
        "no_speech_detected": len(full_text) == 0,
        "segments": [
            {
                "start": w["start"],
                "end": w["end"],
                "text": w["text"],
                "confidence": w["confidence"],
            }
            for w in word_segments
        ],
        "sentences": sentences,
        "engine": {
            "provider": "vosk-offline",
            "sample_rate": config.VOSK_SAMPLE_RATE,
            "word_timestamps": True,
        },
    }

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(transcript_payload, indent=2), encoding="utf-8")

    if progress_callback:
        progress_callback(100, full_text)

    return transcript_payload
