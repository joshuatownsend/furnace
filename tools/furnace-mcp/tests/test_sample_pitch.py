"""Sample pitch detection (idea 005) against synthetic samples with known pitch,
and the center-rate math (no furnace binary)."""

import numpy as np
import pytest

from furnace_mcp import analysis, song as fsong

RNG = np.random.default_rng(5)


def synth(kind, hz, rate, seconds):
    t = np.arange(int(rate * seconds)) / rate
    ks = [k for k in range(1, 60) if k * hz < rate / 2]
    if kind == "sine":
        return 0.8 * np.sin(2 * np.pi * hz * t)
    if kind == "saw":
        return 0.5 * sum(np.sin(2 * np.pi * hz * k * t) / k for k in ks)
    if kind == "piano":
        # decaying partials, the upper ones faster and slightly stretched sharp
        return 0.4 * sum(np.exp(-t * (1.5 + 1.2 * k)) / k
                         * np.sin(2 * np.pi * hz * k * np.sqrt(1 + 0.0002 * k * k) * t) for k in ks[:20])
    if kind == "weak-fundamental":
        amps = {1: 0.03, 2: 1.0, 3: 0.8, 4: 0.6, 5: 0.4, 6: 0.2}  # fundamental 30 dB down
        return 0.3 * sum(a * np.sin(2 * np.pi * hz * k * t) for k, a in amps.items() if k * hz < rate / 2)
    raise ValueError(kind)


def quantize(x, bits):
    # the sample as Furnace stores it
    if bits == 8:
        return np.clip(np.round(x * 127), -128, 127) / 128
    return np.clip(np.round(x * 32767), -32768, 32767) / 32768


def cents_off(x, rate, hz, loop=None):
    r = analysis.detect_pitch(analysis.sample_segment(x, loop)[0], rate)
    assert r["hz"] is not None, r
    return 1200 * np.log2(r["hz"] / hz)


CASES = [(hz, rate) for rate in (8000, 22050, 44100) for hz in (55.0, 130.81, 261.63, 440.0, 987.77)
         if hz < rate / 8]


@pytest.mark.parametrize("kind", ["sine", "saw", "piano", "weak-fundamental"])
@pytest.mark.parametrize("seconds", [0.1, 0.15, 1.0])
@pytest.mark.parametrize("bits", [8, 16])
def test_pitch_within_ten_cents(kind, seconds, bits):
    # the brief's bar: within 10 cents, short samples (under 0.2 s) included
    errs = [cents_off(quantize(synth(kind, hz, rate, seconds), bits), rate, hz) for hz, rate in CASES]
    assert max(map(abs, errs)) < 10, errs


def test_single_cycle_loop():
    # a 32-sample wave cycle, looped: at center rate 8372 it is a C-4
    cycle = quantize(np.sin(2 * np.pi * np.arange(32) / 32) + 0.3 * np.sin(6 * np.pi * np.arange(32) / 32), 8)
    x = np.concatenate([np.zeros(100), cycle])
    r = analysis.detect_pitch(analysis.sample_segment(x, (100, 132, 0))[0], 8372)
    assert r["period"] == pytest.approx(32, abs=0.01)


def test_loop_is_what_gets_measured():
    # an attack at one pitch, a loop at another: the loop holds the note
    rate = 22050
    attack = synth("saw", 300.0, rate, 0.3)
    held = synth("saw", 441.0, rate, 0.2)[:500]  # 10 cycles of 441 Hz
    x = np.concatenate([attack, held])
    loop = (len(attack), len(x), 0)
    assert abs(cents_off(x, rate, 441.0, loop)) < 2
    # ping-pong plays the loop forward then backward: a reversed cycle has the same period
    assert abs(cents_off(x, rate, 441.0, (len(attack), len(x), 2))) < 2


@pytest.mark.parametrize("kind", ["noise", "hat", "chord", "chord-saw"])
def test_no_clear_pitch(kind):
    rate = 22050
    t = np.arange(int(rate * 0.5)) / rate
    if kind == "noise":
        x = RNG.normal(0, 0.3, len(t))
    elif kind == "hat":
        x = RNG.normal(0, 0.5, len(t)) * np.exp(-t * 30)
    else:  # an equal-tempered major triad
        wave = np.sin if kind == "chord" else (lambda p: sum(np.sin(k * p) / k for k in range(1, 8)))
        x = 0.3 * sum(wave(2 * np.pi * 220.0 * 2 ** (s / 12) * t) for s in (0, 4, 7))
    r = analysis.detect_pitch(analysis.sample_segment(quantize(x, 16))[0], rate)
    assert r["hz"] is None and r["reason"], r


def test_silence():
    assert analysis.detect_pitch(np.zeros(4000), 8000)["hz"] is None


def test_center_rate_for_the_docs_example():
    # doc/9-guides/tuning-samples.md: an E recorded at 22050 Hz becomes 17501.10 Hz
    period = 22050 / analysis.note_hz(108 + 16)  # E-5
    t = analysis.sample_tuning(22050, period, 8372.0)
    assert t["plays_note"] == 108 + 16 and abs(t["plays_cents"]) < 0.1
    assert t["new_rate"] == 17501 and t["target_semitones"] == 12
    # the song's tuning cancels out: chip and notes both scale with it
    assert analysis.sample_tuning(22050, period, 8372.0, a4=432.0)["new_rate"] == 17501


def test_center_rate_conventions():
    # a 32-sample cycle at the nominal rate is a C-4 in both conventions
    for nominal in (8372.0, 8363.0):
        t = analysis.sample_tuning(int(nominal), 32, nominal)
        assert t["plays_note"] == 108 and abs(t["plays_cents"]) < 0.01 and t["new_rate"] == int(nominal)
    # 20 cents sharp moves the rate 20 cents down
    t = analysis.sample_tuning(10000, 32 * 10000 / 8372 / 2 ** (20 / 1200), 8372.0)
    assert t["plays_cents"] == pytest.approx(20, abs=0.01)
    assert t["new_rate"] == round(10000 * 2 ** (-20 / 1200))
    # c4_plays transposes: a C-4 sample made to sound an octave lower
    assert analysis.sample_tuning(8372, 32, 8372.0, c4_plays=96)["new_rate"] == 4186


def test_sample_pcm_depths():
    assert list(fsong.sample_pcm({"depth": 8, "data": [0, 127, 128, 255]})) == [0, 127 / 128, -1, -1 / 128]
    x = fsong.sample_pcm({"depth": 16, "data": list(np.array([0, 16384, -32768], "<i2").tobytes())})
    assert list(x) == [0, 0.5, -1]
    with pytest.raises(ValueError, match="depth 9 \\(BRR\\)"):
        fsong.sample_pcm({"depth": 9, "data": [0] * 9})


@pytest.mark.parametrize("period", [2, 3, 5])
def test_very_short_periods(period):
    # chip loops of 2 or 3 samples must not read an octave low
    cycle = {2: [0.8, -0.8], 3: [0.8, -0.4, -0.4], 5: [0.8, 0.3, -0.5, -0.5, -0.1]}[period]
    x = np.tile(cycle, 4000 // period)
    r = analysis.detect_pitch(x, 8000)
    assert r["hz"] is not None, r
    assert abs(1200 * np.log2(r["hz"] / (8000 / period))) < 10


def test_sample_instruments_follow_the_sample_mode():
    mapped = {"type": 4, "amiga": {"initSample": 0, "useNoteMap": True,
                                   "sampleMap": [{"freq": 0, "map": 2}] * 90 + [{"freq": 0, "map": 3}] * 90}}
    plain = {"type": 4, "amiga": {"initSample": 2}}
    synth_off = {"type": 1, "amiga": {"initSample": 2, "useSample": False}}  # an FM instrument
    synth_on = {"type": 5, "amiga": {"initSample": 2, "useSample": True}}
    song = {"instruments": [mapped, plain, synth_off, synth_on]}
    assert fsong.sample_instruments(song, 2) == [0, 1, 3]
    assert fsong.sample_instruments(song, 3) == [0]
    assert fsong.sample_instruments(song, 0) == []  # the note map replaces initSample


def test_tiny_loop_after_a_long_attack():
    # a 3-sample held loop is measured, not the 300 Hz attack before it
    rate = 8000
    attack = synth("saw", 300.0, rate, 0.5)
    x = np.concatenate([attack, [0.8, -0.4, -0.4]])
    assert abs(cents_off(x, rate, rate / 3, (len(attack), len(x), 0))) < 10


def test_ping_pong_half_cycle_loop():
    # a rising half-wave played forward then back is one triangle cycle of twice its length
    ramp = np.linspace(-0.8, 0.8, 16)
    x = np.concatenate([np.zeros(50), ramp])
    r = analysis.detect_pitch(analysis.sample_segment(x, (50, 66, 2))[0], 8000)
    assert r["period"] == pytest.approx(32, abs=0.05)


@pytest.mark.parametrize("rate", [8000, 22050, 44100])
def test_two_sample_period_at_any_rate(rate):
    r = analysis.detect_pitch(np.tile([0.8, -0.8], 4000), rate)
    assert r["hz"] == pytest.approx(rate / 2, rel=0.006)


def test_wavetable_mode_plays_no_sample():
    song = {"instruments": [{"type": 4, "amiga": {"initSample": 2, "useWave": True}}]}
    assert fsong.sample_instruments(song, 2) == []


def test_very_short_one_shot():
    x = np.tile([0.8, 0.2, -0.5, -0.5], 18)  # 72 samples, steady
    seg = analysis.sample_segment(x)[0]
    r = analysis.detect_pitch(seg, 8000)
    assert r["hz"] == pytest.approx(2000, rel=0.006)
