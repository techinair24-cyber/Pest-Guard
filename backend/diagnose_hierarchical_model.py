import json
import joblib
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODEL_DIR = BASE / "ai_model" / "pest_new_dataset_candidate"

bundle_path = MODEL_DIR / "hierarchical_audio_classifier.joblib"
labels_path = MODEL_DIR / "class_names.json"

print("Loading hierarchical classifier...")
bundle = joblib.load(bundle_path)

with open(labels_path, "r", encoding="utf-8") as f:
    labels = json.load(f)

groups = bundle["groups"]
group_by_label = bundle["group_by_label"]

print("\n=== GROUP COUNTS ===")
for group in groups:
    count = sum(g == group for g in group_by_label)
    print(f"{group}: {count} species")

print("\n=== GROUP MODEL ===")
group_model = bundle["group_model"]
print("Pipeline:", type(group_model).__name__)
print("Classes:", group_model[-1].classes_)

print("\n=== SPECIES MAPPING ===")
for label, group in zip(labels, group_by_label):
    print(f"{label} -> {group}")

print("\n=== SPECIALIST MODELS ===")
for group in groups:
    expert = bundle["experts"][group]
    print(f"\n{group}")
    print("Model:", type(expert).__name__)
    print("Class IDs:", expert[-1].classes_)

print("\nDiagnostic inspection completed.")
