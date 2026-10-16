"""A small text "listen report" for a rendered WAV (stand-in until idea 004).

Numbers Claude can reason about: loudness, clipping, silence, and where the
energy sits in the spectrum (spectral centroid, rolloff and band shares).
"""

import wave

import numpy as np

BANDS = [(20, 150, "sub/bass"), (150, 500, "low-mid"), (500, 2000, "mid"),
         (2000, 6000, "presence"), (6000, 20000, "air")]


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        rate, nch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    return x.reshape(-1, nch), rate


def _db(v):
    return 20.0 * np.log10(max(float(v), 1e-9))


def analyze(path):
    x, rate = read_wav(path)
    n = len(x)
    res = {"seconds": round(n / rate, 2)}
    if n == 0:
        return res
    res["peak_dbfs"] = round(_db(np.abs(x).max()), 1)
    res["clipped_samples"] = int(np.count_nonzero(np.abs(x) >= 0.999))
    # loudness and spectrum without DC: some chips (SN76489, AY) output unipolar
    x = x - x.mean(axis=0)
    mono = x.mean(axis=1)
    peak = float(np.abs(x).max())
    res["rms_dbfs"] = round(_db(np.sqrt(np.mean(mono ** 2))), 1)
    # silence: 50 ms windows below -60 dBFS
    win = max(1, rate // 20)
    frames = mono[: n - n % win].reshape(-1, win) if n >= win else mono.reshape(1, -1)
    frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
    res["silent_percent"] = round(100.0 * float(np.mean(frame_rms < 10 ** (-60 / 20))), 1)
    if peak < 1e-6:
        return res
    # spectrum: average of 4096-point Hann-windowed frames
    size = 4096
    hop = size // 2
    if n < size:
        mono = np.pad(mono, (0, size - n))
    idx = np.arange(0, len(mono) - size + 1, hop)
    if len(idx) > 400:
        idx = idx[np.linspace(0, len(idx) - 1, 400).astype(int)]
    window = np.hanning(size)
    spec = np.zeros(size // 2 + 1)
    for i in idx:
        spec += np.abs(np.fft.rfft(mono[i:i + size] * window)) ** 2
    freqs = np.fft.rfftfreq(size, 1.0 / rate)
    total = spec.sum()
    if total <= 0:
        return res
    res["centroid_hz"] = int(float((freqs * spec).sum() / total))
    cum = np.cumsum(spec) / total
    res["rolloff85_hz"] = int(freqs[np.searchsorted(cum, 0.85)])
    res["band_energy_percent"] = {
        name: round(100.0 * float(spec[(freqs >= lo) & (freqs < hi)].sum() / total), 1)
        for lo, hi, name in BANDS
    }
    # dominant pitch region (strongest bin below 5 kHz), useful for bass/lead checks
    low = freqs < 5000
    res["strongest_hz"] = int(freqs[low][np.argmax(spec[low])])
    return res


def format_report(name, r):
    parts = [f"{name}: {r['seconds']}s"]
    if "peak_dbfs" in r:
        parts.append(f"peak {r['peak_dbfs']} dBFS, RMS {r['rms_dbfs']} dBFS")
        if r["clipped_samples"]:
            parts.append(f"CLIPPING {r['clipped_samples']} samples")
        parts.append(f"silent {r['silent_percent']}%")
    if r.get("rms_dbfs", 0) < -50:
        parts.append("near silent")
    elif "centroid_hz" in r:
        bands = ", ".join(f"{k} {v}%" for k, v in r["band_energy_percent"].items())
        parts.append(f"centroid {r['centroid_hz']} Hz, 85% rolloff {r['rolloff85_hz']} Hz, "
                     f"strongest {r['strongest_hz']} Hz; bands: {bands}")
    elif "peak_dbfs" in r:
        parts.append("no audible signal")
    return "; ".join(parts)
