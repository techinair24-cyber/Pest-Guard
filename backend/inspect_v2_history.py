import json
from pathlib import Path

p = Path("backend/ai_model/candidate_combined_v2_history.json")
data = json.loads(p.read_text(encoding="utf-8"))

print("Epochs completed:", data["epochs_completed"])
print("\nEpoch | Train accuracy | Val accuracy | Train loss | Val loss")

h = data["history"]
for i in range(len(h["loss"])):
    print(
        f"{i + 1:5} | "
        f"{h['accuracy'][i]:13.4%} | "
        f"{h['val_accuracy'][i]:11.4%} | "
        f"{h['loss'][i]:10.4f} | "
        f"{h['val_loss'][i]:8.4f}"
    )

best = min(range(len(h["val_loss"])), key=lambda i: h["val_loss"][i])
print(f"\nBest validation-loss epoch: {best + 1}")
print("No model files modified.")
