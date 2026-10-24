import csv
import json
import re
from pathlib import Path

import librosa
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

ROOT = Path(__file__).resolve().parent
DATASET = Path.home() / "Desktop" / "Pest Sound Dataset"
MODEL_DIR = ROOT / "backend" / "ai_model" / "pest_yamnet_updated_candidate"
REPORT = ROOT / "pest_all_predictions_report.csv"

SAMPLE_RATE = 16000
CLIP_SECONDS = 5
EXTENSIONS = {".wav", ".mp3", ".oga", ".ogg", ".flac", ".m4a"}

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def main():
    with open(MODEL_DIR / "class_names.json", encoding="utf-8") as f:
        labels = json.load(f)

    label_lookup = {normalize(label): label for label in labels}
    aliases = {
        "cicada": "Cicada",
        "commonfieldgrasshopper": "Common field grasshopper",
        "desertlocust": "Desert locust",
        "dogdaycicada": "Dog Day Cicada",
        "fieldcricket": "Field Crickt",
        "fruitsfly": "Fruite Fly",
        "grasshopper": "Grasshopper",
        "greatgreenbushcricket": "Great green bush-cricket",
        "housecricket": "House Cricket",
        "katydid": "Katydid",
        "migratorylocust": "Migratory locust",
        "molecricket": "Mole cricket",
        "rhinocerosbeetle": "Rhinoceros beetle",
        "roeselsbushcricket": "Roesel's bush-cricket",
        "shorthornedgrasshopper": "Short-horned grasshopper",
        "snowytreecricket": "Snowy Tree Cricket",
        "swampcicada": "Swamp Cicada",
        "treecricket": "Tree Cricket",
        "twospottedcricket": "Two-spotted cricket",
        "termite": "termite",
        "termites": "termite",
    }
    model = tf.keras.models.load_model(MODEL_DIR / "best_candidate.keras")
    yamnet = hub.load("https://tfhub.dev/google/yamnet/1")

    files = []
    for folder in sorted(DATASET.iterdir()):
        if not folder.is_dir():
            continue
        key = normalize(folder.name)
        key = normalize(aliases.get(key, folder.name))
        actual = label_lookup.get(key)
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                files.append((path, folder.name, actual))

    if not files:
        print("No audio recordings found.")
        return

    correct = 0
    scored = 0
    rows = []
    clip_samples = SAMPLE_RATE * CLIP_SECONDS

    print(f"Testing {len(files)} recordings with the new candidate...")

    for number, (path, folder, actual) in enumerate(files, 1):
        try:
            audio, _ = librosa.load(
                str(path), sr=SAMPLE_RATE, mono=True
            )
            if len(audio) < SAMPLE_RATE:
                raise ValueError("Audio shorter than one second")

            embeddings = []
            for start in range(0, len(audio), clip_samples):
                clip = audio[start:start + clip_samples]
                if len(clip) < SAMPLE_RATE:
                    continue
                _, embedding, _ = yamnet(
                    tf.convert_to_tensor(clip, dtype=tf.float32)
                )
                embeddings.append(np.mean(embedding.numpy(), axis=0))

            if not embeddings:
                raise ValueError("No usable audio clips")

            predictions = model.predict(
                np.asarray(embeddings, dtype=np.float32), verbose=0
            )
            scores = np.mean(predictions, axis=0)
            index = int(np.argmax(scores))
            predicted = labels[index]
            score = float(scores[index])

            is_correct = actual is not None and predicted == actual
            if actual is not None:
                scored += 1
                correct += int(is_correct)

            rows.append({
                "file": str(path),
                "actual_folder": folder,
                "mapped_actual": actual or "UNMAPPED",
                "predicted": predicted,
                "top_score": round(score, 4),
                "correct": is_correct if actual else "UNMAPPED",
                "status": "OK",
            })
        except Exception as exc:
            rows.append({
                "file": str(path),
                "actual_folder": folder,
                "mapped_actual": actual or "UNMAPPED",
                "predicted": "",
                "top_score": "",
                "correct": "",
                "status": str(exc),
            })

        if number % 10 == 0 or number == len(files):
            print(f"Progress: {number}/{len(files)}")

    with open(REPORT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "actual_folder", "mapped_actual",
            "predicted", "top_score", "correct", "status"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print("\nFinished.")
    print(f"Recordings processed: {len(files)}")
    print(f"Correctly mapped recordings scored: {scored}")
    if scored:
        print(f"Full-dataset accuracy: {correct / scored * 100:.1f}%")
    print(f"CSV report: {REPORT}")
    print("Note: this includes training recordings, so accuracy is not an unseen-data score.")

if __name__ == "__main__":
    main()
