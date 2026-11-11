from pathlib import Path

path = Path("src/pages/LiveMonitoring.jsx")
if not path.is_file():
    raise SystemExit(f"Cannot find {path}. Run this script from the Pest guard project root.")

source = path.read_text(encoding="utf-8")

old_name_block = """  const predictedPestDisplayName = predictedPestName
    ? getDisplayPestName(
        predictedPestName,
        pestDirectory,
        displayDetection,
      )
    : ''"""
new_name_block = """  const predictedPestDisplayName = predictedPestName
    ? String(
        displayDetection?.common_name ||
          matchingPestRecord?.commonName ||
          (predictedScientificName
            ? predictedPestName
            : getDisplayPestName(
                predictedPestName,
                pestDirectory,
                displayDetection,
              )),
      ).trim()
    : ''"""

old_detail_block = """              {predictedPestName && (
                <small className="latest-identification-detail">
                  {predictedScientificName
                    ? `Scientific name: ${predictedScientificName}`
                    : `Scientific name unavailable; model class: ${predictedPestName}`}
                </small>
              )}"""
new_detail_block = """              {predictedPestName && predictedScientificName &&
                normalizePestName(predictedScientificName) !==
                  normalizePestName(predictedPestDisplayName) && (
                  <small
                    className="latest-identification-detail"
                    style={{ display: 'block', marginTop: '0.3rem' }}
                  >
                    Scientific name: <em>{predictedScientificName}</em>
                  </small>
                )}"""

if old_name_block not in source:
    raise SystemExit("Expected predictedPestDisplayName block not found; no changes made.")
if old_detail_block not in source:
    raise SystemExit("Expected scientific-name JSX block not found; no changes made.")

source = source.replace(old_name_block, new_name_block, 1)
source = source.replace(old_detail_block, new_detail_block, 1)
path.write_text(source, encoding="utf-8", newline="\n")
print("SUCCESS: Live Monitoring now shows common name first and a separate scientific-name line when distinct.")
print("Existing Detect/Stop logic was not changed.")
