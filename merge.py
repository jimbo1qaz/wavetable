import itertools
from collections import OrderedDict
from enum import Enum
from typing import List

import numpy as np
from wavetable import wave_util
from wavetable.instrument import _get, I, F, S
from wavetable import fourier
from wavetable import transfer as transfers
from wavetable.instrument import MergeInstr
from wavetable.wave_util import Rescaler


def load_string(s):
    """
    >>> (load_string('  0 1 2 3; 4 5 6 7  ;;;  ') == [[0,1,2,3], [4,5,6,7]]).all()
    True

    :param s: a list of number-space waveforms (of equal length), separated by semicolons
    :return: an np.array[i] == one waveform.
    """

    data = s.split(';')
    waves = []
    for d in data:
        wave = I(d)
        if wave.size > 0:
            waves.append(wave)
            assert wave.shape == waves[0].shape
    return np.array(waves)


def _load_waves(filename):
    with open(filename) as f:
        s = f.read()
    return load_string(s)


# **** packing MML strings

def merge_waves_mml(waves, mml=None, vol_curve=None):
    """
    :param waves:
    :param mml:
    :param vol_curve:
    :return:
    """

    if mml:
        inds = I(mml)
        seq = waves[inds]
    else:
        seq = waves

    if vol_curve:
        vol_curve = F(vol_curve)
        cnt = max(len(seq), len(vol_curve))
        seq = np.array([
            _get(seq, i) * _get(vol_curve, i)
            for i in range(cnt)
        ])

    return seq


def load_file_mml(filename, mml=None, vol_curve=None):
    """
    >>>
    :param filename:
    :param mml:
    :param vol_curve:
    :return:
    """
    waves = _load_waves(filename)
    return merge_waves_mml(waves, mml, vol_curve)


def print_waves(waveseq):
    strs = [S(wave) for wave in waveseq]
    print(';\n'.join(strs))
    print()


print_waveseq = print_waves


# class MergeStyle(Enum):
#     POWER = 1
#     AMPLITUDE = 2
#     SUM = 3


_MAXRANGE = 16


class Merge:
    merge_funcs = {
        'POWER':    wave_util.power_merge,
        'AMP':      wave_util.amplitude_merge,
        'SUM':      wave_util.sum_merge
    }

    def __init__(self, maxrange: int,
                 merge_style = 'POWER',
                 scaling='local',
                 fft='new'):

        self.phasor_merger = self.merge_funcs[merge_style]
        self.scaling = scaling
        self.rescaler = Rescaler(maxrange)
        if fft == 'new':
            self.rfft = fourier.rfft_zoh
            self.irfft = fourier.irfft_zoh
        elif fft == 'old':
            self.rfft = fourier.rfft_norm
            self.irfft = fourier.irfft_old
        else:
            raise ValueError(f'fft=[new, old] (you supplied {fft})')

    def _merge_waves(self, waves: List[np.ndarray], nsamp, transfer):
        """ Depends on self.avg_func. """
        ffts = [self.rfft(wave) for wave in waves]

        outs = []
        for f, phasors in enumerate(itertools.zip_longest(*ffts, fillvalue=0j)):
            outs.append(self.phasor_merger(phasors) * transfer(f))

        wave_out = self.irfft(outs, nsamp)
        if self.scaling == 'local':
            return self.rescaler.rescale(wave_out)
        else:
            return wave_out

    def merge_instrs(self, instrs: List[MergeInstr], nsamp, transfer=transfers.Unity()):
        """ Pads each MergeInstr to longest. Then merges all and returns new $waves. """
        length = max(len(instr.waveseq) for instr in instrs)
        merged_waveseq = []

        for wave_idx in range(length):
            harmonic_waves = []

            # entry[wave_idx] = [freq, amp]
            for instr in instrs:
                harmonic_wave = instr.get_wave_scaled(wave_idx)
                harmonic_waves.append(harmonic_wave)

            out = self._merge_waves(harmonic_waves, nsamp=nsamp, transfer=transfer)
            merged_waveseq.append(out)

        if self.scaling == 'global':
            return self.rescaler.rescale(merged_waveseq)
        else:
            return merged_waveseq

    @staticmethod
    def combine(waveseq):
        """ Returns minimal waveseq, MML string. """
        waveseq = [tuple(wave) for wave in waveseq]
        wave2idx = OrderedDict()
        curr_idx = 0

        mml = []

        for wave in waveseq:
            if wave not in wave2idx:
                wave2idx[wave] = curr_idx
                curr_idx += 1
            mml.append(wave2idx[wave])

        minimal_waveseq = list(wave2idx.keys())
        print_waveseq(minimal_waveseq)
        print(S(mml))
        print()
        print()

    def merge_combine(self, instrs: List[MergeInstr], nsamp, transfer=transfers.Unity()):
        """ merge and combine into minimal wave and MML string. """
        self.combine(self.merge_instrs(instrs, nsamp, transfer))


# FIXME maxrange
def merge_combine(instrs: List[MergeInstr], nsamp, maxrange=_MAXRANGE, transfer=transfers.Unity()):
    merger = Merge(maxrange)
    merger.merge_combine(instrs, nsamp, transfer)
