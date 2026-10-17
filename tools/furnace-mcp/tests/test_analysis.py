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


def test_tuning_from_partials():
    # only partials 3 and 4, 5 cents flat: no energy at the fundamental itself
    t = np.arange(RATE // 2) / RATE
    f = 261.63 * 2 ** (-5 / 1200)
    x = np.sin(2 * np.pi * 3 * f * t) + 0.5 * np.sin(2 * np.pi * 4 * f * t)
    cents, fit = analysis._tuning(*analysis._spectrum(x, RATE), 261.63)
    assert cents == pytest.approx(-5, abs=1) and fit > 0.9
    # a partial halfway between grid lines is off the series
    inharmonic = np.sin(2 * np.pi * 261.63 * 2.25 * t)
    assert analysis._tuning(*analysis._spectrum(inharmonic, RATE), 261.63)[1] < 0.2


def test_unsure_tracker_report():
    r = {"note": 108, "expected_hz": 261.63, "clipped_samples": 0,
         "envelope": {"peak_dbfs": -14.8, "attack_ms": 5, "decay_ms": 350, "sustain_db": -14.3,
                      "release_ms": 760},
         "pitch": {"hz": 345.53, "uncertain": True, "tuning_cents": -4.8, "on_grid": 1.0}}
    line = analysis.format_note_report(r).splitlines()[0]
    assert "tracker unsure" in line and "-4.8 cents" in line and "100%" in line


def test_harmonics_relative_to_the_strongest(tmp_path):
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(440.0, 1.0, (1.0, 0.5, 0.0, 0.1)))
    h = analysis.analyze_note(wav, 117)["timbre"]["held"]["harmonics_db"]
    assert h[0] == 0 and h[1] == pytest.approx(-6.0, abs=0.5) and h[3] == pytest.approx(-20.0, abs=1.0)
    assert h[2] < -40
    # a weak fundamental: the others don't read as +40 dB
    wav = write_wav(tmp_path / "b.wav", 0.5 * tone(440.0, 1.0, (0.01, 1.0, 0.5)))
    h = analysis.analyze_note(wav, 117)["timbre"]["held"]["harmonics_db"]
    assert h[0] == pytest.approx(-40.0, abs=1.0) and h[1] == 0 and h[2] == pytest.approx(-6.0, abs=0.5)


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


def unipolar(tmp_path, release_s):
    # idle at 0.1 for 0.1 s (an SN76489 idles above zero), a square between 0.1 and
    # 0.4 for 0.8 s, then the square fading by 60 dB over release_s
    pre, on, total = int(0.1 * RATE), int(0.9 * RATE), int(1.5 * RATE)
    t = np.arange(total) / RATE
    amp = np.zeros(total)
    amp[pre:on] = 0.3
    amp[on:] = 0.3 * 10 ** (-3 * (t[on:] - 0.9) / release_s)
    x = 0.1 + amp * (np.sin(2 * np.pi * 440 * t) > 0)
    return analysis.analyze_note(write_wav(tmp_path / "a.wav", x), 117, note_off_s=0.9, note_on_s=0.1)


def test_unipolar_chip_silence_is_zero(tmp_path):
    # an instant release: the tail must read as silence, not as sustain
    r = unipolar(tmp_path, 0.001)
    assert r["envelope"]["release_ms"] is not None and r["envelope"]["release_ms"] < 30
    assert abs(r["pitch"]["cents"]) < 5


def test_unipolar_release_still_sounding_at_the_end(tmp_path):
    # the tail is not silence, so the reference must come from before the note:
    # 40 of the 60 dB in 0.5 s is about 333 ms
    r = unipolar(tmp_path, 0.5)
    assert r["envelope"]["release_ms"] == pytest.approx(333, abs=40)


def test_anti_phase_stereo_does_not_cancel(tmp_path):
    # one side inverted, as the SNES can do: a mean of the two is silence
    x = 0.4 * tone(440.0, 1.0, (1.0, 0.5))
    pcm = (np.stack([x, -x], axis=1) * 32767).astype("<i2")
    with wave.open(str(tmp_path / "a.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    r = analysis.analyze_note(tmp_path / "a.wav", 117)
    assert abs(r["pitch"]["cents"]) < 1
    assert r["timbre"]["held"]["harmonics_db"][1] == pytest.approx(-6.0, abs=0.5)


def test_song_tuning_is_the_reference():
    assert analysis.note_hz(117, a4=432.0) == pytest.approx(432.0)


def test_pitch_against_song_tuning(tmp_path):
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(432.0, 1.0, (1.0, 0.5)))
    r = analysis.analyze_note(wav, 117, a4=432.0)
    assert abs(r["pitch"]["cents"]) < 1 and r["expected_hz"] == 432.0


def test_hard_panned_loudness(tmp_path):
    # left only: the peak must be the left channel's level, not 6 dB under it
    x = 0.5 * tone(440.0, 1.0)
    pcm = (np.stack([x, np.zeros_like(x)], axis=1) * 32767).astype("<i2")
    with wave.open(str(tmp_path / "a.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    env = analysis.analyze_note(tmp_path / "a.wav", 117)["envelope"]
    # -9 dBFS; 5 ms frames wobble a few tenths. Averaging channels read about -15
    assert env["peak_dbfs"] == pytest.approx(20 * np.log10(0.5 / np.sqrt(2)), abs=0.5)


def test_report_fits(tmp_path):
    wav = write_wav(tmp_path / "a.wav", 0.5 * tone(440.0, 1.0, (1.0, 0.5)))
    text = analysis.format_note_report(analysis.analyze_note(wav, 117, note_off_s=0.6))
    assert len(text.splitlines()) <= 6 and "cents" in text
