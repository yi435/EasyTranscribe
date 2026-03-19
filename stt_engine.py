"""Full Buffer: transcribe accumulated audio with contextual prompting."""

import queue
import threading
from typing import Callable

import numpy as np
import pyaudio
from faster_whisper import WhisperModel

PHRASE_BIAS = [
    # Add common words or phrases here to bias Whisper with an initial prompt.
]

SUPPRESS_TOKENS = [
    # Phrase-based suppression for common hallucinations.
    "thank you for watching",
    "[music]",
    "subscribe",
    "like and subscribe",
]


class AudioRecorder:
    """Records audio in a background thread and stores bytes in a queue."""

    def __init__(
        self,
        rate: int = 16000,
        channels: int = 1,
        frames_per_buffer: int = 1024,
    ) -> None:
        self.rate = rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stop_event = threading.Event()
        self._audio: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._audio is not None:
            return

        self._audio = pyaudio.PyAudio()
        if not self._has_input_device():
            self._audio.terminate()
            self._audio = None
            raise RuntimeError("No microphone detected.")

        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.frames_per_buffer,
        )
        self._stop_event.clear()

        # The recording loop runs in a background thread and is stopped by
        # signaling the threading.Event. This prevents blocking the UI.
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()

        if self._audio is not None:
            self._audio.terminate()

        self._thread = None
        self._stream = None
        self._audio = None

    def read_available(self) -> bytes:
        data = bytearray()
        while True:
            try:
                data.extend(self._queue.get_nowait())
            except queue.Empty:
                break
        return bytes(data)

    def _has_input_device(self) -> bool:
        if self._audio is None:
            return False

        for index in range(self._audio.get_device_count()):
            info = self._audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) > 0:
                return True
        return False

    def _record_loop(self) -> None:
        if self._stream is None:
            return

        while not self._stop_event.is_set():
            data = self._stream.read(
                self.frames_per_buffer,
                exception_on_overflow=False,
            )
            self._queue.put(data)


class STTEngine:
    """Streaming transcription using faster-whisper with full-buffer logic."""

    def __init__(self) -> None:
        self._model = WhisperModel("base", device="cpu", compute_type="int8")
        self._recorder = AudioRecorder()
        self._buffer_lock = threading.Lock()
        self._audio_buffer = bytearray()
        self._last_text = ""

    def reset(self) -> None:
        with self._buffer_lock:
            self._audio_buffer = bytearray()
        self._last_text = ""

    def stream_transcribe(
        self,
        stop_event: threading.Event,
        on_update: Callable[[str], None],
        on_final: Callable[[str], None],
        on_error: Callable[[str], None],
        interval_seconds: float = 2.0,
    ) -> None:
        prompt = " ".join(PHRASE_BIAS).strip()
        try:
            self._recorder.start()
            while not stop_event.is_set():
                stop_event.wait(interval_seconds)
                if stop_event.is_set():
                    break

                chunk = self._recorder.read_available()
                if chunk:
                    with self._buffer_lock:
                        self._audio_buffer.extend(chunk)

                with self._buffer_lock:
                    audio_bytes = bytes(self._audio_buffer)

                if not audio_bytes:
                    continue

                audio = self._normalize_audio(
                    self._bytes_to_float32(audio_bytes)
                )
                initial_prompt = self._last_text or prompt or None
                segments, _info = self._model.transcribe(
                    audio,
                    vad_filter=True,
                    initial_prompt=initial_prompt,
                )

                full_text = self._segments_to_text(segments)
                if full_text and full_text != self._last_text:
                    self._last_text = full_text
                    on_update(full_text)
        except Exception as exc:
            on_error(str(exc))
        finally:
            final_text = ""
            with self._buffer_lock:
                final_audio_bytes = bytes(self._audio_buffer)
            if final_audio_bytes:
                final_audio = self._normalize_audio(
                    self._bytes_to_float32(final_audio_bytes)
                )
                segments, _info = self._model.transcribe(
                    final_audio,
                    vad_filter=True,
                )
                final_text = self._segments_to_text(segments)
            on_final(final_text)
            self._recorder.stop()

    @staticmethod
    def _bytes_to_float32(data: bytes) -> np.ndarray:
        audio_int16 = np.frombuffer(data, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        return audio_float32

    @staticmethod
    def _normalize_audio(audio: np.ndarray) -> np.ndarray:
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak == 0.0:
            return audio
        return audio / peak

    @staticmethod
    def _segments_to_text(segments) -> str:
        filtered: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            if STTEngine._is_suppressed(text):
                continue
            filtered.append(text)
        return " ".join(filtered).strip()

    @staticmethod
    def _is_suppressed(text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in SUPPRESS_TOKENS)
