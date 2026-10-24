from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

TEST_FILE = Path("backend/test_prediction_safety.py")

if not TEST_FILE.is_file():
    raise SystemExit(
        "ERROR: backend/test_prediction_safety.py not found. "
        "Run this script from the Pest guard project root."
    )

source = TEST_FILE.read_text(encoding="utf-8")

pattern_loop = re.compile(
    r'(?m)^(?P<indent>[ \t]*)self\.assertEqual\(response\["status"\], "UNKNOWN"\)\n'
    r'(?P=indent)self\.assertEqual\(response\["pest"\], pest\)$'
)
replacement_loop = (
    '{indent}self.assertEqual(response["status"], "UNKNOWN")\n'
    '{indent}if confidence < main.PEST_IDENTIFICATION_CONFIDENCE:\n'
    '{indent}    self.assertIsNone(response["pest"])\n'
    '{indent}    self.assertEqual(\n'
    '{indent}        response["identification_label"], "Unidentified sound"\n'
    '{indent}    )\n'
    '{indent}    self.assertEqual(response["risk"], "UNKNOWN")\n'
    '{indent}    self.assertIsNone(response["risk_rationale"])\n'
    '{indent}else:\n'
    '{indent}    self.assertEqual(response["pest"], pest)\n'
    '{indent}    self.assertEqual(\n'
    '{indent}        response["identification_label"], "Possible match"\n'
    '{indent}    )'
)

matches_loop = list(pattern_loop.finditer(source))
if len(matches_loop) != 1:
    raise SystemExit(
        f"ERROR: Expected exactly one low/high-score assertion block, found {len(matches_loop)}. "
        "No files changed."
    )

def replace_loop(match):
    return replacement_loop.format(indent=match.group("indent"))

updated, count_loop = pattern_loop.subn(replace_loop, source)
if count_loop != 1:
    raise SystemExit("ERROR: Could not update the low/high-score assertions. No files changed.")

pattern_pcm = re.compile(
    r'(?m)^(?P<indent>[ \t]*)self\.assertEqual\(response\["status"\], "UNKNOWN"\)\n'
    r'(?P=indent)self\.assertIn\(response\["pest"\], main\.class_names\)$'
)
replacement_pcm = (
    '{indent}self.assertEqual(response["status"], "UNKNOWN")\n'
    '{indent}if response["confidence"] < main.PEST_IDENTIFICATION_CONFIDENCE:\n'
    '{indent}    self.assertIsNone(response["pest"])\n'
    '{indent}    self.assertEqual(\n'
    '{indent}        response["identification_label"], "Unidentified sound"\n'
    '{indent}    )\n'
    '{indent}    self.assertEqual(response["risk"], "UNKNOWN")\n'
    '{indent}    self.assertIsNone(response["risk_rationale"])\n'
    '{indent}else:\n'
    '{indent}    self.assertIn(response["pest"], main.class_names)\n'
    '{indent}    self.assertEqual(\n'
    '{indent}        response["identification_label"], "Possible match"\n'
    '{indent}    )'
)

matches_pcm = list(pattern_pcm.finditer(updated))
if len(matches_pcm) != 1:
    raise SystemExit(
        f"ERROR: Expected exactly one JSON-PCM contract assertion block, found {len(matches_pcm)}. "
        "No files changed."
    )

def replace_pcm(match):
    return replacement_pcm.format(indent=match.group("indent"))

final_text, count_pcm = pattern_pcm.subn(replace_pcm, updated)
if count_pcm != 1:
    raise SystemExit("ERROR: Could not update the JSON-PCM assertions. No files changed.")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = TEST_FILE.with_name(f"{TEST_FILE.name}.backup_before_confidence_test_update_{timestamp}")
shutil.copy2(TEST_FILE, backup)
TEST_FILE.write_text(final_text, encoding="utf-8", newline="")

print("SUCCESS: updated tests to expect candidate rejection below the configured threshold.")
print("SUCCESS: high-score predictions remain present but explicitly unconfirmed.")
print("SUCCESS: low-score results must omit candidate species and candidate risk metadata.")
print(f"Backup: {backup.resolve()}")
print("NEXT: run backend/test_prediction_safety.py; do not commit or deploy until tests pass.")
