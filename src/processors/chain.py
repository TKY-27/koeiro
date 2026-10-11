import numpy as np
import time

from src.audio.performance import TimingStats
from src.vc.models import is_meanvc2

from .base import AudioProcessor
from .denoise import NoiseSuppressionProcessor
from .gain import GainProcessor
from .noise_gate import NoiseGateProcessor
from .passthrough import PassthroughProcessor


class SafetyClampProcessor(AudioProcessor):
    def prepare(self, sample_rate, max_frames):
        self._finite = np.empty((max_frames, 1), dtype=bool)

    def process(self, audio, sample_rate):
        # Reuse a boolean mask rather than nan_to_num's temporary masks.
        mask = self._finite[:len(audio)]
        np.isfinite(audio, out=mask)
        np.logical_not(mask, out=mask)
        np.copyto(audio, 0.0, where=mask)
        np.clip(audio, -1.0, 1.0, out=audio)
        return audio


class ProcessorChain(AudioProcessor):
    def __init__(self, main_processor=None, gain_db=0.0, threshold_db=-45.0, denoise_strength=0.0,
                 whisper=None, finish=None):
        # Denoise first, then the gate, then gain: the gate sees a cleaner signal
        # and the strength-0 default makes the stage a true pass-through.
        self.denoise = NoiseSuppressionProcessor(denoise_strength)
        self.gate = NoiseGateProcessor(threshold_db)
        self.gain = GainProcessor(gain_db)
        # Whisper mode sits before everything: restoring a pitch before the gate and
        # the model see the signal is the point. It is off by default (amount 0), and
        # a chain without it is exactly what this build shipped before.
        self.whisper = whisper
        self.pre_processors = ((self.whisper, self.denoise, self.gate, self.gain) if whisper is not None
                               else (self.denoise, self.gate, self.gain))
        self.main_processor = main_processor if main_processor is not None else PassthroughProcessor()
        # The natural finish conditions converted output only: Original never
        # passes through it, and a chain without it is the previous behaviour.
        from .natural_finish import NaturalFinishProcessor
        self.finish = finish if finish is not None else NaturalFinishProcessor()
        self.post_processors = (self.finish, SafetyClampProcessor())
        self._stages = (*self.pre_processors, self.main_processor, *self.post_processors)
        self.performance = TimingStats()

    def prepare(self, sample_rate, max_frames):
        self.performance.reset()
        for processor in self._stages:
            processor.prepare(sample_rate, max_frames)

    def reset(self):
        for processor in self._stages:
            processor.reset()

    def stop(self):
        for processor in self._stages:
            processor.stop()

    def process(self, audio, sample_rate):
        shape = audio.shape
        router = self.main_processor
        ai = getattr(router, 'ai', None)
        self.gate.protect_quiet = (getattr(router, 'mode', None) == 'ai_voice'
                                   and ai is not None and is_meanvc2(ai.bridge.parameters.model))
        # The finish only ever conditions converted output. The flag rides along
        # per block so a mid-stream route change takes effect on the next block.
        self.finish.route_active = getattr(router, 'mode', 'ai_voice') != 'original'
        for processor in self._stages:
            started = time.perf_counter_ns() if processor is self.main_processor else 0
            audio = processor.process(audio, sample_rate)
            if started:
                self.performance.record(time.perf_counter_ns() - started, len(audio), sample_rate)
            if not isinstance(audio, np.ndarray) or audio.shape != shape or audio.dtype != np.float32:
                raise ValueError("Processor must return float32 mono with unchanged frame count")
        return audio
