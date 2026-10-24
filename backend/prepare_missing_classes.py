from pathlib import Path
import re
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

wav_root = Path.home() / "Desktop" / "InsectSet66_Train_Val_Test" / "InsectSet66_Train_Val_Test"
out_root = Path.home() / "Desktop" / "InsectSound1000_Training" / "InsectSet459_Processed"

classes = [
    "Platypleuracfcatenata",
    "Platypleuraplumosa",
    "Platypleurasp10",
    "Platypleurasp12cfhirtipennis",
    "Platypleurasp13",
]

source_rate = 44100
target_rate = 16000
segment_length = 80000
minimum_last_segment = 16000

total_created = 0

for class_name in classes:
    files = sorted(wav_root.glob(class_name + "*.wav"))
    class_dir = out_root / class_name
    class_dir.mkdir(parents=True, exist_ok=True)
    created = 0

    if not files:
        raise RuntimeError(f"No WAV files found for {class_name}")

    for wav_path in files:
        audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)

        if sr != target_rate:
            divisor = gcd(int(sr), target_rate)
            audio = resample_poly(
                audio,
                target_rate // divisor,
                int(sr) // divisor
            ).astype(np.float32)

        stem = re.sub(r"[^A-Za-z0-9._-]", "_", wav_path.stem)[:120]

        segment_number = 0
        for start in range(0, len(audio), segment_length):
            chunk = audio[start:start + segment_length]

            if len(chunk) < minimum_last_segment:
                break

            if len(chunk) < segment_length:
                padded = np.zeros(segment_length, dtype=np.float32)
                padded[:len(chunk)] = chunk
                chunk = padded

            output = class_dir / f"{stem}_seg{segment_number:03d}.npy"

            if output.exists():
                segment_number += 1
                continue

            np.save(output, np.asarray(chunk, dtype=np.float32))
            created += 1
            segment_number += 1

    print(f"{class_name}: {len(files)} WAV files, {created} new segments")
    total_created += created

print(f"TOTAL NEW SEGMENTS: {total_created}")
print("Original WAV files and production model were not modified.")
