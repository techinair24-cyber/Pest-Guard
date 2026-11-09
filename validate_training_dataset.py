
from pathlib import Path
from collections import Counter
import hashlib
import math
import numpy as np
import librosa
import soundfile as sf

DATASET_ROOT = Path(
    r"C:\Users\Deepthi MG\Desktop\Pest Guard Dataset"
)

AUDIO_EXTENSIONS = {
    ".wav", ".wavex", ".mp3", ".flac",
    ".ogg", ".aiff", ".aif"
}

MIN_DURATION_SECONDS = 0.5
MAX_DURATION_SECONDS = 300.0
DECODE_SAMPLE_RATE = None
BLOCK_SECONDS = 10

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def decode_audio(path):
    audio, sample_rate = librosa.load(
        str(path),
        sr=DECODE_SAMPLE_RATE,
        mono=False
    )
    if audio.size == 0:
        raise ValueError("Decoded audio is empty")
    return audio, sample_rate

def inspect_audio(path):
    audio, sample_rate = decode_audio(path)

    if audio.ndim == 1:
        channels = 1
        mono = audio
    elif audio.ndim == 2:
        channels = audio.shape[0]
        mono = np.mean(audio, axis=0)
    else:
        raise ValueError(f"Unexpected audio dimensions: {audio.ndim}")

    duration = len(mono) / sample_rate
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))
    silent = peak < 1e-5
    near_silent = rms < 1e-4
    clipped = float(np.mean(np.abs(mono) >= 0.999))

    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "duration": duration,
        "peak": peak,
        "rms": rms,
        "silent": silent,
        "near_silent": near_silent,
        "clipped_fraction": clipped,
    }

def main():
    if not DATASET_ROOT.is_dir():
        raise FileNotFoundError(DATASET_ROOT)

    files = sorted(
        path for path in DATASET_ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in AUDIO_EXTENSIONS
    )

    print(f"Dataset: {DATASET_ROOT}")
    print(f"Files found: {len(files)}")
    print("Starting full audio decoding and quality checks...\n")

    sample_rates = Counter()
    channel_counts = Counter()
    durations = []
    errors = []
    short_files = []
    long_files = []
    silent_files = []
    near_silent_files = []
    clipped_files = []
    exact_hashes = {}

    for index, path in enumerate(files, start=1):
        try:
            result = inspect_audio(path)

            sample_rates[result["sample_rate"]] += 1
            channel_counts[result["channels"]] += 1
            durations.append(result["duration"])

            if result["duration"] < MIN_DURATION_SECONDS:
                short_files.append(str(path))

            if result["duration"] > MAX_DURATION_SECONDS:
                long_files.append(str(path))

            if result["silent"]:
                silent_files.append(str(path))

            if result["near_silent"]:
                near_silent_files.append(str(path))

            if result["clipped_fraction"] > 0.01:
                clipped_files.append(str(path))

            file_hash = sha256_file(path)
            exact_hashes.setdefault(file_hash, []).append(str(path))

        except Exception as exc:
            errors.append((str(path), repr(exc)))

        if index % 100 == 0 or index == len(files):
            print(f"Processed {index}/{len(files)}")

    duplicate_groups = [
        paths for paths in exact_hashes.values()
        if len(paths) > 1
    ]

    print("\n========== QUALITY VALIDATION ==========")
    print(f"Total files discovered: {len(files)}")
    print(f"Successfully processed: {len(durations)}")
    print(f"Decode/inspection failures: {len(errors)}")

    print("\n--- SAMPLE RATES ---")
    for rate, count in sample_rates.most_common():
        print(f"{rate} Hz: {count}")

    print("\n--- CHANNEL COUNTS ---")
    for channels, count in channel_counts.most_common():
        print(f"{channels} channel(s): {count}")

    print("\n--- DURATION ---")
    if durations:
        print(f"Minimum: {min(durations):.3f} seconds")
        print(f"Median: {np.median(durations):.3f} seconds")
        print(f"Maximum: {max(durations):.3f} seconds")
        print(f"Mean: {np.mean(durations):.3f} seconds")

    print("\n--- QUALITY FLAGS ---")
    print(f"Below {MIN_DURATION_SECONDS}s: {len(short_files)}")
    print(f"Above {MAX_DURATION_SECONDS}s: {len(long_files)}")
    print(f"Silent: {len(silent_files)}")
    print(f"Near-silent: {len(near_silent_files)}")
    print(f"Clipped above 1%: {len(clipped_files)}")

    print("\n--- EXACT DUPLICATES ---")
    print(f"Duplicate groups: {len(duplicate_groups)}")
    print(f"Files in duplicate groups: {sum(map(len, duplicate_groups))}")

    print("\n--- FAILURE DETAILS (first 20) ---")
    for path, error in errors[:20]:
        print(f"{path}\n  {error}")

    print("\n--- FINAL RESULT ---")
    print(f"Discovered: {len(files)}")
    print(f"Successful: {len(durations)}")
    print(f"Failures: {len(errors)}")
    print("Original dataset was not modified.")

if __name__ == "__main__":
    main()
