from pathlib import Path
from collections import Counter, defaultdict
import soundfile as sf

DATASET_ROOT = Path(
    r"C:\Users\Deepthi MG\Desktop\Pest Guard Dataset"
)

AUDIO_EXTENSIONS = {
    ".wav", ".wavex", ".mp3", ".flac", ".ogg", ".aiff", ".aif"
}
def main():
    if not DATASET_ROOT.is_dir():
        raise FileNotFoundError(DATASET_ROOT)

    files = sorted(
        path for path in DATASET_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )

    sample_rates = Counter()
    channels = Counter()
    formats = Counter()
    subtypes = Counter()
    errors = []
    durations = defaultdict(list)

    print(f"Dataset: {DATASET_ROOT}")
    print(f"Audio files discovered: {len(files)}")

    for index, path in enumerate(files, start=1):
        try:
            info = sf.info(str(path))

            sample_rates[info.samplerate] += 1
            channels[info.channels] += 1
            formats[info.format] += 1
            subtypes[info.subtype] += 1
            durations[path.parent.name].append(info.duration)

        except Exception as exc:
            errors.append((str(path), str(exc)))

        if index % 500 == 0:
            print(f"Inspected {index}/{len(files)}")

    print("\n--- SAMPLE RATES ---")
    for value, count in sample_rates.most_common():
        print(f"{value} Hz: {count}")

    print("\n--- CHANNELS ---")
    for value, count in channels.most_common():
        print(f"{value} channel(s): {count}")

    print("\n--- FILE FORMATS ---")
    for value, count in formats.most_common():
        print(f"{value}: {count}")

    print("\n--- SUBTYPES ---")
    for value, count in subtypes.most_common():
        print(f"{value}: {count}")

    print("\n--- DECODE ERRORS ---")
    print(f"Count: {len(errors)}")
    for path, error in errors[:20]:
        print(f"{path}\n  {error}")

    print("\n--- RESULT ---")
    print(f"Total discovered: {len(files)}")
    print(f"Successfully inspected: {len(files) - len(errors)}")
    print(f"Failed: {len(errors)}")

if __name__ == "__main__":
    main()
