from pathlib import Path
import sys

TARGET = Path.cwd() / "src" / "pages" / "LiveMonitoring.jsx"

if not TARGET.is_file():
    print("ERROR: Run this script from the Pest guard project root, where src/pages/LiveMonitoring.jsx exists.")
    sys.exit(1)

try:
    source = TARGET.read_text(encoding="utf-8")
except UnicodeDecodeError:
    print("ERROR: Could not read LiveMonitoring.jsx as UTF-8. No files changed.")
    sys.exit(1)

main_needle = '''          <div className="latest-detection-main">
            <span className="detection-indicator" />
            <div>
              <strong>'''
main_replacement = '''          <div className="latest-detection-main">
            <span className="detection-indicator" />
            <div>
              {predictedPestName && (
                <small
                  className="top-match-label"
                  style={{
                    display: 'block',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    marginBottom: '0.25rem',
                  }}
                >
                  TOP MATCH
                </small>
              )}
              <strong>'''

score_needle = '<span>Model score (not calibrated confidence)</span>'
score_replacement = '<span>Top-match model score (not calibrated confidence)</span>'

main_count = source.count(main_needle)
score_count = source.count(score_needle)
if main_count != 1 or score_count != 1:
    print(
        "ERROR: Expected code anchors were not found exactly once "
        f"(prediction section: {main_count}, score label: {score_count}). No files changed."
    )
    print("Please share the latest-detection JSX and model-score label again for a targeted patch.")
    sys.exit(1)

backup = TARGET.with_name("LiveMonitoring.jsx.before-top-match.bak")
if backup.exists():
    print(f"ERROR: Backup already exists: {backup.name}. No files changed to avoid overwriting it.")
    print("Rename that backup first if you want to run this patch again.")
    sys.exit(1)

updated = source.replace(main_needle, main_replacement, 1).replace(score_needle, score_replacement, 1)
backup.write_text(source, encoding="utf-8", newline="")
TARGET.write_text(updated, encoding="utf-8", newline="")

print("SUCCESS: Updated only src/pages/LiveMonitoring.jsx")
print("- Shows TOP MATCH above the predicted pest name when a pest prediction exists.")
print("- Labels the displayed value as the top-match model score; the numeric score is unchanged.")
print(f"- Backup saved as: {backup.name}")
print("Next: restart the frontend and test one dataset recording. No model, backend, or detection logic was changed.")
