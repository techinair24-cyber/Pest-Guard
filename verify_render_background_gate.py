"""Send one known background WAV to the deployed Pest Guard API.

Expected safe result: HTTP 422 from the background gate, before the insect
classifier, database commit, or websocket broadcast. This script does not send
any insect recordings.
"""
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly
from math import gcd

API_URL = "https://pest-guard-1q36.onrender.com/api/ai/predict"
DEFAULT_WAV = Path.home() / "Desktop" / "InsectSound1000_Training" / "ESC50_background_pilot" / "1-115521-A-19.wav"
TARGET_RATE = 16000
TARGET_SAMPLES = 80000


def to_mono_float(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio)
    if x.ndim == 2:
        x = x.astype(np.float32).mean(axis=1)
    elif x.ndim != 1:
        raise ValueError(f"Unsupported audio shape: {x.shape}")
    if np.issubdtype(x.dtype, np.integer):
        info = np.iinfo(x.dtype)
        if info.min < 0:
            scale = float(max(abs(info.min), info.max))
            x = x.astype(np.float32) / scale
        else:
            midpoint = (float(info.max) + 1.0) / 2.0
            x = (x.astype(np.float32) - midpoint) / midpoint
    else:
        x = x.astype(np.float32)
    x = np.nan_to_num(x, copy=False)
    return x


def make_pcm16_body(path: Path) -> bytes:
    rate, source = wavfile.read(str(path))
    audio = to_mono_float(source)
    if int(rate) != TARGET_RATE:
        factor = gcd(int(rate), TARGET_RATE)
        audio = resample_poly(audio, TARGET_RATE // factor, int(rate) // factor).astype(np.float32)
    if len(audio) < TARGET_SAMPLES:
        padded = np.zeros(TARGET_SAMPLES, dtype=np.float32)
        padded[:len(audio)] = audio
        audio = padded
    else:
        audio = audio[:TARGET_SAMPLES]
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak
    pcm = np.clip(audio * 32767.0, -32768, 32767).astype("<i2")
    return pcm.tobytes()


def main() -> int:
    path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_WAV
    if not path.is_file():
        print(f"Background WAV not found: {path}")
        print("Pass the full path to one of the downloaded ESC-50 background WAV files.")
        return 2

    print("Render background-gate smoke test")
    print(f"Service: {API_URL}")
    print(f"Test file: {path.name}")
    try:
        body = make_pcm16_body(path)
        request = Request(
            API_URL,
            data=body,
            headers={"Content-Type": "application/octet-stream", "User-Agent": "PestGuard-Gate-SmokeTest/1.0"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                status = response.status
                text = response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            status = error.code
            text = error.read().decode("utf-8", errors="replace")

        print(f"HTTP status: {status}")
        print(f"Response: {text[:1200]}")
        if status == 422 and "background" in text.lower():
            print("PASS: deployed backend rejected background audio before creating a detection.")
            return 0
        if status == 503:
            print("FAIL: backend or gate is unavailable; keep ESP32 diagnostic-only.")
            return 1
        if 200 <= status < 300:
            print("FAIL: background audio was accepted. Do not re-enable ESP32 live requests.")
            return 1
        print("INCONCLUSIVE: response does not confirm a successful gate rejection. Keep ESP32 diagnostic-only.")
        return 1
    except (URLError, TimeoutError, OSError, ValueError) as error:
        print(f"FAIL: could not complete the live test: {type(error).__name__}: {error}")
        print("Keep ESP32 diagnostic-only until the deployed service is verified.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
