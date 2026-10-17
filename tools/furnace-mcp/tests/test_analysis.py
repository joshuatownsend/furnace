"""The one-note analysis against synthetic signals with known answers (no furnace binary)."""

import wave

import numpy as np
import pytest

from furnace_mcp import analysis

RATE = 44100


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


def tone(hz, seconds, harmonics=(1.0,)):
    t = np.arange(int(RATE * seconds)) / RATE
    return sum(a * np.sin(2 * np.pi * hz * (k + 1) * t) for k, a in enumerate(harmonics))


def adsr(n_on, n_total, attack_s, decay_s, sustain, release_s):
    env = np.zeros(n_total)
    a, d = int(attack_s * RATE), int(decay_s * RATE)
    env[:a] = np.linspace(0, 1, a, endpoint=False)
    env[a:a + d] = np.linspace(1, sustain, d, endpoint=False)
    env[a + d:n_on] = sustain
    r = n_total - n_on
    # exponential release: 60 dB over release_s
    env[n_on:] = sustain * 10 ** (-3 * np.arange(r) / (release_s * RATE))
    return env


def test_note_numbers():
    assert analysis.note_hz(117) == pytest.approx(440.0)
    assert analysis.note_hz(108) == pytest.approx(261.63, abs=0.01)


@pytest.mark.parametrize("cents", [0.0, 10.0, -25.0])
def test_pitch_in_cents(tmp_path, cents):
    hz = 440.0 * 2 ** (cents / 1200)
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(hz, 1.0, (1.0, 0.5, 0.3)))
    r = analysis.analyze_note(wav, 117)
    assert r["pitch"]["cents"] == pytest.approx(cents, abs=1.0)


def test_missing_fundamental_still_finds_the_pitch(tmp_path):
    # harmonics 2-5 only: a "strongest frequency" check would say 880 Hz
    wav = write_wav(tmp_path / "a.wav", 0.4 * tone(220.0, 1.0, (0.0, 1.0, 0.8, 0.6, 0.4)))
    r = analysis.analyze_note(wav, 105)  # A-3
    assert abs(r["pitch"]["cents"]) < 2


def test_harmonics_relative_to_fundamental(tmp_path):
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(440.0, 1.0, (1.0, 0.5, 0.0, 0.1)))
    h = analysis.analyze_note(wav, 117)["timbre"]["held"]["harmonics_db"]
    assert h[0] == 0 and h[1] == pytest.approx(-6.0, abs=0.5) and h[3] == pytest.approx(-20.0, abs=1.0)
    assert h[2] < -40


def test_envelope(tmp_path):
    on, total = int(0.8 * RATE), int(1.5 * RATE)
    x = 0.6 * tone(440.0, 1.5) * adsr(on, total, 0.05, 0.2, 0.5, 0.3)
    r = analysis.analyze_note(write_wav(tmp_path / "a.wav", x), 117, note_off_s=0.8)
    env = r["envelope"]
    assert 30 <= env["attack_ms"] <= 60
    assert 120 <= env["decay_ms"] <= 220
    assert env["sustain_db"] == pytest.approx(-6.0, abs=0.7)
    assert 150 <= env["release_ms"] <= 260  # 40 of the 60 dB in 0.3 s = 0.2 s


def test_silence_and_noise(tmp_path):
    assert analysis.analyze_note(write_wav(tmp_path / "s.wav", np.zeros(RATE)), 117)["silent"]
    noise = np.random.default_rng(1).uniform(-0.5, 0.5, RATE)
    r = analysis.analyze_note(write_wav(tmp_path / "n.wav", noise), 117)
    assert r["pitch"] is None
    assert "no clear pitch" in analysis.format_note_report(r)


def test_attack_and_held_timbre_differ(tmp_path):
    # bright for 100 ms, then a pure tone: the attack must show it, the held part not
    t = np.arange(RATE) / RATE
    bright = sum(np.sin(2 * np.pi * 440 * k * t) / k for k in range(1, 9))
    x = 0.4 * np.where(t < 0.1, bright, np.sin(2 * np.pi * 440 * t))
    timbre = analysis.analyze_note(write_wav(tmp_path / "a.wav", x), 117, note_off_s=0.9)["timbre"]
    assert timbre["attack"]["harmonics_db"][2] > -15
    assert timbre["held"]["harmonics_db"][2] < -40


def test_near_silent_window_reports_no_tone(tmp_path):
    # decays to -50 dB and holds there: the held window is noise floor, not tone.
    # The decay ends inside that window, so its loud start must not count.
    on, total = int(0.9 * RATE), int(1.2 * RATE)
    x = 0.6 * tone(440.0, 1.2, (1.0, 0.5)) * adsr(on, total, 0.005, 0.65, 10 ** (-50 / 20), 0.2)
    r = analysis.analyze_note(write_wav(tmp_path / "a.wav", x), 117, note_off_s=0.9)
    assert r["timbre"]["held"]["too_quiet"] and "harmonics_db" in r["timbre"]["attack"]
    assert "too quiet to measure tone" in analysis.format_note_report(r)


def test_report_fits(tmp_path):
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(440.0, 1.0, (1.0, 0.5)))
    text = analysis.format_note_report(analysis.analyze_note(wav, 117, note_off_s=0.6))
    assert len(text.splitlines()) <= 6 and "cents" in text
