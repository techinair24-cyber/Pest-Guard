import json
import random
import re
from pathlib import Path

PROJECT = Path.cwd()
LABELS_PATH = PROJECT / "backend" / "ai_model" / "class_names.json"
DATA_ROOT = Path.home() / "Desktop" / "InsectSound1000_Training" / "InsectSet459_Processed"
OUT_PATH = PROJECT / "backend" / "ai_model" / "candidate_validation_manifest.json"

SEED = 42
VALIDATION_FRACTION = 0.15

labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
label_index = {
    re.sub(r"[^a-z0-9]", "", name.lower()): i
    for i, name in enumerate(labels)
}

random.seed(SEED)
train_paths, train_labels = [], []
val_paths, val_labels = [], []

for folder in sorted(p for p in DATA_ROOT.iterdir() if p.is_dir()):
    key = re.sub(r"[^a-z0-9]", "", folder.name.lower())
    if key not in label_index:
        continue

    files = sorted(folder.glob("*.npy"))
    if not files:
        continue

    groups = {}
    for file in files:
        stem = re.sub(r"_seg\d+$", "", file.stem, flags=re.IGNORECASE)
        groups.setdefault(stem, []).append(file)

    group_names = sorted(groups)
    random.shuffle(group_names)
    val_count = max(1, round(len(group_names) * VALIDATION_FRACTION)) if len(group_names) >= 2 else 0
    val_groups = set(group_names[:val_count])
    class_id = label_index[key]

    for group_name, group_files in groups.items():
        if group_name in val_groups:
            val_paths.extend(str(p.resolve()) for p in group_files)
            val_labels.extend([class_id] * len(group_files))
        else:
            train_paths.extend(str(p.resolve()) for p in group_files)
            train_labels.extend([class_id] * len(group_files))

manifest = {
    "seed": SEED,
    "validation_fraction": VALIDATION_FRACTION,
    "classes": labels,
    "train_paths": train_paths,
    "train_labels": train_labels,
    "validation_paths": val_paths,
    "validation_labels": val_labels,
}

OUT_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Manifest:", OUT_PATH)
print("Training segments:", len(train_paths))
print("Validation segments:", len(val_paths))
print("Classes:", len(labels))
print("Saved successfully.")
