export const UNKNOWN_INSECT_GROUP = 'Unknown insect group'

export function getDetectionInsectGroup(detection) {
  return String(detection?.insect_group || '').trim() || UNKNOWN_INSECT_GROUP
}

export function getTopSpeciesPredictions(predictions) {
  if (!Array.isArray(predictions)) return []

  return predictions
    .filter((prediction) => (
      typeof prediction?.pest === 'string' &&
      prediction.pest.trim() !== '' &&
      Number.isFinite(Number(prediction.score))
    ))
    .slice()
    .sort((first, second) => Number(second.score) - Number(first.score))
    .slice(0, 3)
}

export function formatModelScore(value) {
  const score = Number(value)
  if (!Number.isFinite(score) || score < 0) return 'N/A'
  const percentage = score > 1 ? score : score * 100
  return `${Math.min(percentage, 100).toFixed(1)}%`
}

export function getPredictionUncertainty(detection) {
  if (!detection?.pest || String(detection?.identification_status || '').toUpperCase() === 'CONFIRMED') {
    return ''
  }

  return 'Unverified result — model scores are uncalibrated ranking estimates, not confirmed identifications.'
}

export function getCandidateDisplayName(candidate) {
  const scientificName = String(candidate?.pest || '').trim()
  const commonName = String(candidate?.common_name || '').trim()

  if (!scientificName) return 'Unidentified species candidate'
  if (!commonName || commonName.toLowerCase() === scientificName.toLowerCase()) {
    return scientificName
  }
  return `${commonName} (${scientificName})`
}
