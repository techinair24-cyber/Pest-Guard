from pathlib import Path
from datetime import datetime
import shutil

TEST_FILE = Path("backend/test_prediction_safety.py")

if not TEST_FILE.is_file():
    raise SystemExit(
        "ERROR: backend/test_prediction_safety.py not found. "
        "Run this script from the Pest guard project root."
    )

source = TEST_FILE.read_text(encoding="utf-8")

old = '''                    self.assertEqual(response["confidence"], confidence)
                    metadata = main.MODEL_SPECIES_METADATA.get(
                        main._normalize_pest_label(pest)
                    )
                    self.assertEqual(
                        response["risk"],
                        metadata["risk"] if metadata else "UNKNOWN",
                    )'''

new = '''                    self.assertEqual(response["confidence"], confidence)
                    metadata = main.MODEL_SPECIES_METADATA.get(
                        main._normalize_pest_label(pest)
                    )
                    if confidence < main.PEST_IDENTIFICATION_CONFIDENCE:
                        self.assertEqual(response["risk"], "UNKNOWN")
                        self.assertIsNone(response["risk_rationale"])
                    else:
                        self.assertEqual(
                            response["risk"],
                            metadata["risk"] if metadata else "UNKNOWN",
                        )'''

count = source.count(old)
if count != 1:
    raise SystemExit(
        f"ERROR: Expected exactly one stale risk assertion, found {count}. "
        "No files changed."
    )

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = TEST_FILE.with_name(
    f"{TEST_FILE.name}.backup_before_confidence_risk_assertion_{timestamp}"
)
shutil.copy2(TEST_FILE, backup)
TEST_FILE.write_text(source.replace(old, new, 1), encoding="utf-8", newline="")

print("SUCCESS: risk assertions now expect UNKNOWN for rejected low-score predictions.")
print("SUCCESS: scores at/above threshold still check the configured metadata risk.")
print(f"Backup: {backup.resolve()}")
print("NEXT: rerun backend/test_prediction_safety.py. Do not commit or deploy yet.")
