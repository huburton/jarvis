"""Speech to text (faster-whisper) and text to speech (Piper). Needs the `voice` extra."""
import re
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

from .textutil import split_sentences

# Typical Whisper hallucinations on silence / noise
_HALLUCINATIONS = re.compile(
    r"sous-titr|amara\.org|merci d'avoir regard|abonnez-vous|merci de votre attention|^\W*$",
    re.IGNORECASE,
)


class STT:
    def __init__(self, model: str, device: str, compute_type: str, threads: int, prompt: str):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(model, device=device, compute_type=compute_type, cpu_threads=threads)
        self._prompt = prompt

    def transcribe(self, audio_int16: np.ndarray) -> str:
        audio = audio_int16.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio, language="fr", beam_size=1, vad_filter=True,
            condition_on_previous_text=False, initial_prompt=self._prompt,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return "" if _HALLUCINATIONS.search(text) else text


class TTS:
    def __init__(self, voice_path: str, length_scale: float = 1.0):
        from piper import PiperVoice, SynthesisConfig
        self._voice = PiperVoice.load(str(Path(voice_path).expanduser()))
        self._syn = SynthesisConfig(length_scale=length_scale)
        self._rate = self._voice.config.sample_rate
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        sd.stop()

    def speak(self, text: str):
        """Speak sentence by sentence (interruptible with stop())."""
        self._stop.clear()
        for sentence in split_sentences(text):
            if self._stop.is_set():
                return
            chunks = [c.audio_float_array for c in self._voice.synthesize(sentence, syn_config=self._syn)]
            if not chunks or self._stop.is_set():
                continue
            sd.play(np.concatenate(chunks), self._rate)
            sd.wait()

