import json
from collections import Counter
from pathlib import Path

root = Path("backend/ai_model")
manifest = json.loads(
    (root / "combined_split_manifest.json").read_text(encoding="utf-8")
)
labels = json.loads(
    (root / "class_names.json").read_text(encoding="utf-8")
)

for split_name in ("train", "validation"):
    items = manifest[split_name]
    counts = Counter(x["label_index"] for x in items)

    print(f"\n{split_name.upper()} CLASS COUNTS")
    print(f"Total samples: {len(items)}")

    for i, name in enumerate(labels):
        print(f"{name}: {counts.get(i, 0)}")

print("\nDataset balance inspection complete. No files modified.")
