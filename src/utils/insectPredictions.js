export const UNKNOWN_INSECT_GROUP = 'Unknown insect group'

const INSECT_GROUP_LABELS = new Set([
  'beetles',
  'cicada',
  'crickets',
  'flies',
  'grasshopper',
  'katydid',
  'mole crickets',
  'termite',
])

export function getDetectionInsectGroup(detection) {
  return String(detection?.insect_group || '').trim() || UNKNOWN_INSECT_GROUP
}

function getCandidateScore(candidate) {
  for (const value of [candidate?.score, candidate?.probability, candidate?.confidence]) {
    if (
      value !== null &&
      value !== undefined &&
      value !== '' &&
      Number.isFinite(Number(value))
    ) {
      return Number(value)
    }
  }

  return null
}

export function getTopSpeciesPredictions(predictions) {
  if (!Array.isArray(predictions)) return []

  return predictions
    .map((prediction) => {
      const score = getCandidateScore(prediction)
      return score === null ? null : { ...prediction, score }
    })
    .filter((prediction) => (
      prediction !== null &&
      typeof prediction.pest === 'string' &&
      prediction.pest.trim() !== '' &&
      prediction.subtype_confidence !== null &&
      !INSECT_GROUP_LABELS.has(prediction.pest.trim().toLowerCase())
    ))
    .slice()
    .sort((first, second) => second.score - first.score)
    .slice(0, 3)
}

export function formatModelScore(value) {
  if (value === null || value === undefined || value === '') return 'N/A'
  const score = Number(value)
  if (!Number.isFinite(score) || score < 0) return 'N/A'
  const percentage = score > 1 ? score : score * 100
  return `${Math.min(percentage, 100).toFixed(1)}%`
}

export function getPredictionUncertainty(detection) {
  if (!detection?.pest || String(detection?.identification_status || '').toUpperCase() === 'CONFIRMED') {
    return ''
  }

 return ''
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
