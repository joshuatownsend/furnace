"""Text "listen reports" for rendered WAVs: numbers Claude can reason about.

analyze(): a mix or excerpt (idea 003): loudness, clipping, silence, and where
the energy sits in the spectrum (spectral centroid, rolloff and band shares).
analyze_note(): one rendered note (idea 004): pitch against the note played,
harmonics, brightness and the attack/decay/sustain/release shape.
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


# --- one-note analysis (idea 004) -----------------------------------------

def note_hz(note, a4=440.0):
    """Equal-tempered frequency of a Furnace note number (C-4 = 108 = middle C);
    a4 is the song's tuning (songInfo.tuning)."""
    return a4 * 2.0 ** ((note - 48 - 69) / 12.0)


def _frames_db(x, rate, ms=5):
    """5 ms RMS levels. For a (samples, channels) array, the louder channel per
    frame: averaging channels would understate a panned sound by up to 6 dB."""
    win = max(1, int(rate * ms / 1000))
    n = len(x) - len(x) % win
    frames = x[:n].reshape(n // win, win, *x.shape[1:])
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    if rms.ndim == 2:
        rms = rms.max(axis=1)
    return 20.0 * np.log10(np.maximum(rms, 1e-9)), ms / 1000.0


def envelope(x, rate, note_off_s):
    """Attack/decay/sustain/release estimate from 5 ms RMS frames.

    attack: onset (40 dB below the peak) to the peak. decay: peak until the
    level settles within 3 dB of the sustain level. sustain: median level over
    the last 30% of the held part, relative to the peak. release: note-off until
    the level falls 40 dB below its note-off level (None if it never does)."""
    db, step = _frames_db(x, rate)
    off = min(len(db), int(note_off_s / step))
    if off < 4 or db[:off].max() < -80:
        return None
    held = db[:off]
    peak_i = int(np.argmax(held))
    peak = float(held[peak_i])
    onset = int(np.argmax(held > peak - 40))
    sustain = float(np.median(held[int(off * 0.7):]))
    settle = peak_i
    if sustain < peak - 3:
        above = np.nonzero(held[peak_i:] > sustain + 3)[0]
        settle = peak_i + (int(above[-1]) + 1 if len(above) else 0)
    level_at_off = float(np.median(db[max(0, off - 4):off]))
    rel = db[off:]
    below = np.nonzero(rel < level_at_off - 40)[0] if len(rel) else []
    return {
        "peak_dbfs": round(peak, 1),
        "attack_ms": int(round((peak_i - onset) * step * 1000)),
        "decay_ms": int(round((settle - peak_i) * step * 1000)),
        "sustain_db": round(sustain - peak, 1),
        "release_ms": int(round(below[0] * step * 1000)) if len(below) else None,
    }


def _yin(x, rate, fmin=25.0, fmax=5000.0, threshold=0.15):
    """Fundamental frequency by YIN (cumulative-mean-normalised difference)."""
    n = len(x)
    tmax = min(int(rate / fmin), n // 2)
    tmin = max(2, int(rate / fmax))
    if tmax <= tmin + 2:
        return None
    w = n - tmax
    # difference function d(t) = sum (x[i] - x[i+t])^2 over a window of w samples
    size = 1 << int(np.ceil(np.log2(n + w)))
    acf = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:w], size)), size)[:tmax + 1]
    sq = np.cumsum(np.concatenate(([0.0], x.astype(np.float64) ** 2)))
    t = np.arange(tmax + 1)
    d = sq[w] + (sq[t + w] - sq[t]) - 2 * acf
    d[0] = 0.0
    cmnd = np.ones_like(d)
    cmnd[1:] = d[1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[1:]), 1e-12)
    tau = None
    for i in range(tmin, tmax):
        if cmnd[i] < threshold:
            while i + 1 < tmax and cmnd[i + 1] < cmnd[i]:
                i += 1
            tau = i
            break
    if tau is None:
        tau = tmin + int(np.argmin(cmnd[tmin:tmax]))
        if cmnd[tau] > 0.5:
            return None  # no clear periodicity
    a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
    den = a - 2 * b + c
    return rate / (tau + (0.5 * (a - c) / den if den else 0.0))


def _spectrum(x, rate, pad=8):
    size = 1 << int(np.ceil(np.log2(len(x) * pad)))
    mag = np.abs(np.fft.rfft(x * np.hanning(len(x)), size))
    return mag, rate / size


def _peak_near(mag, binhz, hz, tol=0.03):
    """Strongest spectral peak within ±tol of hz: (interpolated Hz, magnitude)."""
    lo = max(int(hz * (1 - tol) / binhz), 1)
    hi = min(int(hz * (1 + tol) / binhz) + 1, len(mag) - 1)
    if hi <= lo:
        return None, 0.0
    i = lo + int(np.argmax(mag[lo:hi]))
    a, b, c = (np.log(mag[j] + 1e-12) for j in (i - 1, i, i + 1))
    den = a - 2 * b + c
    return (i + (0.5 * (a - c) / den if den else 0.0)) * binhz, float(mag[i])


def _tuning(mag, binhz, ref, top=5000.0):
    """How far the partials sit from the harmonic series of the note played.

    The grid is ref/2, so an operator at mult 0 (x0.5) still lands on it.
    Returns (cents, fit): the magnitude-weighted offset of the strong partials
    from their grid lines, and the share of energy below `top` that sits on the
    grid. None if no partial is found."""
    g = ref / 2
    hi_bin = min(int(top / binhz), len(mag) - 1)
    total = float((mag[1:hi_bin] ** 2).sum())
    devs, weights, on_grid = [], [], 0.0
    for k in range(1, int(top / g) + 1):
        half = min(0.015 * k * g, g / 4) / binhz
        lo, hi = max(int(k * g / binhz - half), 1), min(int(k * g / binhz + half) + 1, hi_bin)
        if hi - lo < 3:
            continue
        on_grid += float((mag[lo:hi] ** 2).sum())
        i = lo + int(np.argmax(mag[lo:hi]))
        if i in (lo, hi - 1):
            continue  # the slope of a neighbouring peak, not a partial
        a, b, c = (np.log(mag[j] + 1e-12) for j in (i - 1, i, i + 1))
        den = a - 2 * b + c
        hz = (i + (0.5 * (a - c) / den if den else 0.0)) * binhz
        devs.append(1200 * np.log2(hz / (k * g)))
        weights.append(float(mag[i]))
    if not weights:
        return None
    w = np.array(weights)
    strong = w >= w.max() * 10 ** (-30 / 20)
    cents = float(np.average(np.array(devs)[strong], weights=w[strong] ** 2))
    return cents, on_grid / max(total, 1e-24)


QUIET_DB = 40  # a window this far below the peak is too quiet to measure tone


def analyze_note(path, note, note_off_s=None, a4=440.0):
    """Listen report for one rendered note that starts at time 0: pitch against
    the note played, harmonics, brightness, envelope and loudness."""
    x, rate = read_wav(path)
    off = note_off_s if note_off_s is not None else len(x) / rate
    # Unipolar chips (SN76489, AY) idle at a nonzero level. Take the resting level
    # from the silent tail, so silence stays zero; a whole-file mean would leave an
    # offset after note-off that reads as sound. Windows remove their own mean below.
    tail = x[-int(0.05 * rate):]
    rest = np.median(tail, axis=0) if len(x) / rate - off >= 0.1 else x.mean(axis=0)
    clipped = int(np.count_nonzero(np.abs(x) >= 0.999))
    x = x - rest
    mono = x.mean(axis=1)
    hz = note_hz(note, a4)
    res = {"note": note, "expected_hz": round(hz, 2)}
    env = envelope(x, rate, off)
    if env is None:
        res["silent"] = True
        return res
    res["envelope"] = env
    res["clipped_samples"] = clipped
    # pitch comes from the held part after the attack
    end = int(off * rate)
    start = min(int((env["attack_ms"] / 1000 + 0.02) * rate), end)
    seg = mono[start:min(end, start + rate // 2)]
    if len(seg) < rate // 20:
        seg = mono[:end]
    seg = seg - seg.mean() if len(seg) else seg
    f0 = _yin(seg[:rate // 5], rate) if len(seg) else None
    mag, binhz = _spectrum(seg, rate)
    if f0 is not None:
        refined, _ = _peak_near(mag, binhz, f0)
        if refined:
            f0 = refined
    tuning = _tuning(mag, binhz, hz) if len(seg) else None
    cents = None if f0 is None else float(1200 * np.log2(f0 / hz))
    if cents is not None and abs(cents - 1200 * round(cents / 1200)) < 50:
        res["pitch"] = {"hz": round(f0, 2), "cents": round(cents, 1)}
    elif tuning and tuning[1] >= 0.6:
        # the tracker found a period that isn't an octave of the note, but the
        # partials sit on the note's harmonic series: sparse high partials (all
        # carriers above mult 1) fool period trackers, not the ear
        res["pitch"] = {"hz": None if f0 is None else round(f0, 2), "uncertain": True,
                        "tuning_cents": round(tuning[0], 1), "on_grid": round(tuning[1], 2)}
    elif f0 is not None:
        res["pitch"] = {"hz": round(f0, 2), "cents": round(cents, 1)}
    else:
        res["pitch"] = None
        return res
    f0 = f0 if f0 is not None and not res["pitch"].get("uncertain") else hz
    # timbre at two moments: FM modulators often decay fast, so the attack can
    # sound quite different from the held note
    onset = int(np.argmax(np.abs(mono) > np.abs(mono).max() * 0.01))
    windows = {"attack": (onset, onset + rate // 10)}
    if end - onset > int(0.4 * rate):
        windows["held"] = (end - int(0.3 * rate), end)
    res["timbre"] = {}
    for k, (a, b) in windows.items():
        w = mono[a:b]
        # median, like sustain: a loud decay tail at the window's start mustn't count
        level = float(np.median(_frames_db(x[a:b], rate)[0])) - env["peak_dbfs"]
        # near the noise floor the "harmonics" are noise, and they read as a real tone
        res["timbre"][k] = ({"too_quiet": True} if level < -QUIET_DB else _timbre(w - w.mean(), rate, f0))
        res["timbre"][k]["level_db"] = round(level, 1)
    return res


def _timbre(seg, rate, f0):
    """First 8 harmonics in dB relative to the fundamental, and brightness
    (spectral centroid as a multiple of the fundamental)."""
    mag, binhz = _spectrum(seg, rate)
    harm, h1 = [], None
    for k in range(1, 9):
        if k * f0 >= rate / 2:
            break
        _, m = _peak_near(mag, binhz, k * f0, tol=0.015)
        h1 = h1 or max(m, 1e-12)
        harm.append(round(20 * np.log10(max(m, 1e-12) / h1), 1))
    p = mag ** 2
    centroid = float((np.arange(len(mag)) * binhz * p).sum() / max(p.sum(), 1e-24) / f0)
    return {"harmonics_db": harm, "centroid_harmonic": round(centroid, 2)}


def _below_peak(db):
    # digital silence after a clean note-off reads as -150 dB or so
    return "silent (over 80 dB below peak)" if db < -80 else f"{db} dB below peak"


def format_note_report(r):
    if r.get("silent"):
        return f"note {r['note']}: silent (no sound before note-off)"
    env = r["envelope"]
    lines = []
    p = r.get("pitch")
    if p is None:
        lines.append(f"pitch: no clear pitch (expected {r['expected_hz']} Hz)")
    elif p.get("uncertain"):
        found = f"found {p['hz']} Hz, not an octave of it" if p["hz"] else "no clear period"
        lines.append(f"pitch: tracker unsure ({found}); the partials sit {p['tuning_cents']:+.1f} cents "
                     f"off the harmonic series of {r['expected_hz']} Hz "
                     f"({p['on_grid']:.0%} of the energy is on it)")
    else:
        c = p["cents"]
        octs = round(c / 1200)
        extra = f" (about {octs:+d} octave)" if octs and abs(c - 1200 * octs) < 50 else ""
        lines.append(f"pitch: {p['hz']} Hz, {c:+.1f} cents from {r['expected_hz']} Hz{extra}")
    if env["release_ms"] is not None:
        rel = f"{env['release_ms']} ms"
    elif env["sustain_db"] < -QUIET_DB:
        rel = "n/a (already near silent before note-off)"
    else:
        rel = "didn't fall 40 dB before the end"
    lines.append(f"envelope: attack {env['attack_ms']} ms, decay {env['decay_ms']} ms, "
                 f"sustain {_below_peak(env['sustain_db'])}, release {rel}")
    lines.append(f"loudness: peak {env['peak_dbfs']} dBFS (5 ms RMS)"
                 + (f"; CLIPPING {r['clipped_samples']} samples" if r["clipped_samples"] else ""))
    labels = {"attack": "attack (first 100 ms)", "held": "held (last 300 ms before release)"}
    for k, t in (r.get("timbre") or {}).items():
        if t.get("too_quiet"):
            lines.append(f"{labels[k]}: too quiet to measure tone ({_below_peak(t['level_db'])})")
            continue
        lines.append(f"{labels[k]}: harmonics 1-8 in dB vs fundamental "
                     + " ".join(f"{v:g}" for v in t["harmonics_db"])
                     + f"; brightness {t['centroid_harmonic']}x fundamental")
    return "\n".join(lines)
