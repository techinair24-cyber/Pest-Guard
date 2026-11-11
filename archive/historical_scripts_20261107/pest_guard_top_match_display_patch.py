"""Safely update Pest Guard's Live Monitoring UI to display the model's top pest match.

Run from the Pest guard repository root:
    python .\\pest_guard_top_match_display_patch.py

Edits ONLY src/pages/LiveMonitoring.jsx and creates a timestamped backup first.
Does not change the model, backend, confidence values, risk logic, or firmware.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import sys

TARGET = Path("src/pages/LiveMonitoring.jsx")

DISPLAY_STATUS_FUNCTION = '''function displayStatus(status, pest) {
  const normalizedStatus = String(status || '').toUpperCase()
  const hasPest = typeof pest === 'string' && pest.trim().length > 0

  if (normalizedStatus === 'UNKNOWN' && hasPest) return 'TOP MATCH'
  if (normalizedStatus === 'HARMFUL_PEST') return 'HARMFUL PEST'
  if (normalizedStatus === 'NON_PEST') return 'NON-PEST'
  if (normalizedStatus === 'UNKNOWN') return 'UNKNOWN SOUND'
  return 'NO DETECTION'
}'''

DISPLAY_DETECTION_FUNCTION = '''function getDetectionDisplayStatus(detection) {
  if (!detection) return 'NO DETECTION'

  const status = String(detection.status || '').toUpperCase()
  const hasPest = typeof detection.pest === 'string' && detection.pest.trim().length > 0

  if (status === 'UNKNOWN' && hasPest) return 'TOP MATCH'
  if (status === 'HARMFUL_PEST') return 'HARMFUL PEST'
  if (status === 'NON_PEST') return 'NON-PEST'
  if (status === 'UNKNOWN') return 'UNKNOWN SOUND'
  return 'NO DETECTION'
}'''

DETECTION_MESSAGE_FUNCTION = '''function getDetectionMessage(status, pest) {
  const normalizedStatus = String(status || '').toUpperCase()
  const hasPest = typeof pest === 'string' && pest.trim().length > 0

  if (normalizedStatus === 'HARMFUL_PEST') return 'Harmful pest activity detected in the field.'
  if (normalizedStatus === 'NON_PEST') return 'No harmful pest detected.'
  if (normalizedStatus === 'UNKNOWN' && hasPest) {
    return 'Showing the highest-scoring pest match for this audio. The percentage is the model score.'
  }
  if (normalizedStatus === 'UNKNOWN') return 'No pest match was returned for this audio.'
  return 'Waiting for an event from the field unit.'
}'''


def replace_function(source: str, name: str, replacement: str) -> tuple[str, int]:
    pattern = re.compile(
        rf"(?ms)^function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{.*?^\}}"
    )
    return pattern.subn(replacement, source, count=1)


def main() -> int:
    if not TARGET.is_file():
        print(f"ERROR: {TARGET} was not found. Run this script from the Pest guard project root.")
        return 2

    original = TARGET.read_text(encoding="utf-8-sig")
    updated = original
    changes: list[str] = []

    # Support both the simpler displayStatus(status, pest) UI and the newer
    # getDetectionDisplayStatus(detection) UI, without touching unrelated code.
    if re.search(r"(?m)^function\s+displayStatus\s*\(", updated):
        updated, count = replace_function(updated, "displayStatus", DISPLAY_STATUS_FUNCTION)
        if count != 1:
            print("ERROR: Could not safely replace displayStatus(). No files changed.")
            return 3
        changes.append("displayStatus now says TOP MATCH for an UNKNOWN event with a pest class")

    if re.search(r"(?m)^function\s+getDetectionDisplayStatus\s*\(", updated):
        updated, count = replace_function(updated, "getDetectionDisplayStatus", DISPLAY_DETECTION_FUNCTION)
        if count != 1:
            print("ERROR: Could not safely replace getDetectionDisplayStatus(). No files changed.")
            return 4
        changes.append("getDetectionDisplayStatus now says TOP MATCH for an UNKNOWN event with a pest class")

    if re.search(r"(?m)^function\s+getDetectionMessage\s*\(", updated):
        updated, count = replace_function(updated, "getDetectionMessage", DETECTION_MESSAGE_FUNCTION)
        if count != 1:
            print("ERROR: Could not safely replace getDetectionMessage(). No files changed.")
            return 5
        changes.append("message now explains that the shown pest is the highest-scoring model class")

    # Older UI versions showed a status label instead of the pest name for UNKNOWN predictions.
    old_headline = re.compile(
        r"<strong>\{detectionStatus\s*===\s*'HARMFUL_PEST'\s*\?\s*liveDetection\.pest\s*\|\|\s*'Pest not identified'\s*:\s*displayStatus\(detectionStatus\)\}</strong>"
    )
    updated, headline_count = old_headline.subn(
        "<strong>{liveDetection.pest || displayStatus(detectionStatus, liveDetection.pest)}</strong>",
        updated,
    )
    if headline_count:
        changes.append("latest-detection headline now displays the pest class whenever one exists")

    if "AI Confidence" in updated:
        updated = updated.replace("AI Confidence", "Top Match Score")
        changes.append("score heading now reads Top Match Score")

    # Make older call sites pass the pest value used by the display helper.
    updated, message_call_count = re.subn(
        r"getDetectionMessage\(detectionStatus\)",
        "getDetectionMessage(detectionStatus, liveDetection?.pest)",
        updated,
    )
    if message_call_count:
        changes.append("detection message now receives the current pest class")

    if updated == original or not changes:
        print("ERROR: No recognized display code was changed. No files changed.")
        print("Please send the current src/pages/LiveMonitoring.jsx helper functions for a targeted patch.")
        return 6

    # Validate that the top-match behavior exists before touching the file.
    if "TOP MATCH" not in updated or "Top Match Score" not in updated:
        print("ERROR: Validation failed; no files changed.")
        return 7

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"{TARGET.name}.before_top_match_display_{timestamp}.bak")
    if backup.exists():
        print(f"ERROR: Backup path already exists: {backup}. No files changed.")
        return 8

    try:
        shutil.copy2(TARGET, backup)
        TARGET.write_text(updated, encoding="utf-8", newline="")
    except Exception as error:
        if backup.exists():
            try:
                shutil.copy2(backup, TARGET)
            except Exception:
                pass
        print(f"ERROR: Patch failed: {error}. Attempted to restore the original file.")
        return 9

    print("SUCCESS: Updated only src/pages/LiveMonitoring.jsx.")
    for change in changes:
        print(f" - {change}")
    print(f"Backup: {backup.resolve()}")
    print("The score remains the model's actual top-class score; no score is inflated.")
    print("Next: run npm run build, review the page, then commit/push the frontend for Vercel deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
