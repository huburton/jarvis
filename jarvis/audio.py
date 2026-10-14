"""Microphone (PortAudio), wake word and end-of-utterance detection. Needs the `voice` extra."""
import os
import queue
import subprocess
import time

import numpy as np
import sounddevice as sd

RATE = 16000
BLOCK = 1280  # 80 ms: frame size expected by openWakeWord
VAD_FRAME = 512  # Silero: 32 ms windows


class Mic:
    def __init__(self, device=None):
        device = device or None  # empty config value = system default
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self._stream = sd.InputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
            device=device, callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def start(self):
        self._stream.start()

    def read(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self):
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break


class WakeWord:
    def __init__(self, model: str, threshold: float, patience: int = 1):
        from openwakeword.model import Model
        # vad_threshold: the score only counts when Silero hears speech (fewer false positives)
        self._model = Model(wakeword_models=[model], inference_framework="onnx", vad_threshold=0.5)
        self._name = next(iter(self._model.models))
        self.threshold = threshold
        self.patience = patience

    def detect(self, chunk: np.ndarray) -> bool:
        # patience: the score must exceed the threshold on N consecutive frames (fewer false positives)
        scores = self._model.predict(chunk, patience={self._name: self.patience},
                                     threshold={self._name: self.threshold})
        return scores[self._name] >= self.threshold

    def reset(self):
        self._model.reset()


class Endpointer:
    """Record one utterance: starts when speech is detected, stops after a silence."""

    def __init__(self, silence_ms: int, max_s: float):
        from faster_whisper.vad import get_vad_model
        self._vad = get_vad_model()
        self.silence_ms = silence_ms
        self.max_s = max_s

    def _speech_prob(self, window: np.ndarray) -> float:
        audio = window.astype(np.float32) / 32768.0
        n = len(audio) - len(audio) % VAD_FRAME
        if n <= 0:
            return 0.0
        return float(np.max(self._vad(audio[-n:])))

    def record(self, mic: Mic, start_timeout_s: float, should_abort=lambda: False) -> np.ndarray | None:
        chunks: list[np.ndarray] = []
        started = False
        silence = 0.0
        t0 = time.monotonic()
        while True:
            if should_abort():
                return None
            chunk = mic.read(timeout=1.0)
            if chunk is None:
                continue
            chunks.append(chunk)
            window = np.concatenate(chunks[-3:])  # ~240 ms of context
            if self._speech_prob(window) >= 0.5:
                started, silence = True, 0.0
            elif started:
                silence += len(chunk) / RATE * 1000
            elapsed = time.monotonic() - t0
            if started and silence >= self.silence_ms:
                break
            if not started and elapsed > start_timeout_s:
                return None
            if elapsed > self.max_s:
                break
        return np.concatenate(chunks)


def chime(path: str):
    if path and os.path.exists(path):
        subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
