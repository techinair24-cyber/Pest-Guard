from pathlib import Path
import re
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

wav_root = Path.home() / "Desktop" / "InsectSet66_Train_Val_Test" / "InsectSet66_Train_Val_Test"
out_root = Path.home() / "Desktop" / "InsectSound1000_Training" / "Chorthippus_extra_segments"

target_class = "Chorthippusalbomarginatus"
target_folder = out_root / target_class
target_folder.mkdir(parents=True, exist_ok=True)

recording_ids = {
    "XC751374", "XC751375", "XC751376", "XC751377",
    "XC751393", "XC751394", "XC751395", "XC751400",
    "XC751405",
}

files = sorted(
    p for p in wav_root.glob("*Chorthippusalbomarginatus*.wav")
    if any(recording_id in p.stem for recording_id in recording_ids)
)

if not files:
    raise RuntimeError("No matching missing WAV recordings found.")

target_rate = 16000
segment_length = 80000
minimum_last_segment = 16000
total_created = 0

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
    created = 0

    for start in range(0, len(audio), segment_length):
        chunk = audio[start:start + segment_length]

        if len(chunk) < minimum_last_segment:
            break

        if len(chunk) < segment_length:
            padded = np.zeros(segment_length, dtype=np.float32)
            padded[:len(chunk)] = chunk
            chunk = padded

        output = target_folder / f"{stem}_seg{start // segment_length:03d}.npy"
        np.save(output, np.asarray(chunk, dtype=np.float32))
        created += 1

    print(f"{wav_path.name}: {created} segments")
    total_created += created

print(f"\nTOTAL: {len(files)} source files, {total_created} segments")
print(f"Saved separately to: {target_folder}")
print("Existing dataset and models were not modified.")
