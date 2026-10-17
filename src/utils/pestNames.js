export function normalizePestName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

export function buildPestDirectory(items) {
  const directory = {}

  if (!Array.isArray(items)) return directory

  items.forEach((item) => {
    const name = String(item?.name || '').trim()
    const scientificName = String(
      item?.scientific_name || '',
    ).trim()

    const commonName =
      name &&
      normalizePestName(name) !==
        normalizePestName(scientificName)
        ? name
        : ''

    const entry = {
      commonName,
      scientificName,
      pestId: String(item?.pest_id || '').trim(),
      description: item?.description || '',
      symptoms: item?.symptoms || '',
      risk: item?.risk || '',
    }

    ;[name, scientificName, entry.pestId].forEach(
      (candidate) => {
        const key = normalizePestName(candidate)
        if (key) directory[key] = entry
      },
    )
  })

  return directory
}

export function getPestRiskEstimate(
  pest,
  directory = {},
) {
  const key = normalizePestName(pest)

  if (!key) {
    return {
      risk: 'UNKNOWN',
      source: null,
      rationale: '',
    }
  }

  const catalogRisk = String(
    directory[key]?.risk || '',
  ).toUpperCase()

  if (['LOW', 'MEDIUM', 'HIGH'].includes(catalogRisk)) {
    return {
      risk: catalogRisk,
      source: 'Pest Guard pest catalogue',
      rationale:
        'Risk category recorded in the matching pest catalogue entry.',
    }
  }

  return {
    risk: 'UNKNOWN',
    source: null,
    rationale: '',
  }
}

export function getDetectionRiskEstimate(
  detection,
  directory = {},
) {
  const resolvedRisk = String(detection?.risk || '').toUpperCase()
  if (['LOW', 'MEDIUM', 'HIGH'].includes(resolvedRisk)) {
    return {
      risk: resolvedRisk,
      source: detection?.metadata_source_name || null,
      sourceUrl: detection?.metadata_source_url || null,
      rationale: detection?.risk_rationale || '',
    }
  }
  if (resolvedRisk === 'UNKNOWN' && detection?.risk_rationale) {
    return {
      risk: 'UNKNOWN',
      source: null,
      sourceUrl: null,
      rationale: detection.risk_rationale,
    }
  }

  const pestRecord = directory[normalizePestName(detection?.pest)]
  const independentlyVerified =
    detection?.pest_verified === true &&
    Boolean(detection?.pest_id) &&
    detection.pest_id === pestRecord?.pestId

  if (!independentlyVerified) {
    return {
      risk: 'UNKNOWN',
      source: null,
      rationale: '',
    }
  }

  return getPestRiskEstimate(detection.pest, directory)
}

export function getCommonPestName(
  pest,
  directory = {},
  metadata = {},
) {
  const rawName = String(pest || '').trim()

  if (!rawName) return 'Detected pest'

  const key = normalizePestName(rawName)
  const entry = directory[key]

  return String(metadata?.common_name || '').trim() ||
    entry?.commonName ||
    rawName
}

export function getDisplayPestName(
  pest,
  directory = {},
  metadata = {},
) {
  const rawName = String(pest || '').trim()

  if (!rawName) return 'Unknown pest'

  const key = normalizePestName(rawName)
  const entry = directory[key]
  const commonName = getCommonPestName(rawName, directory, metadata)

  const scientificName = String(
    metadata?.scientific_name || entry?.scientificName || '',
  ).trim()

  if (!scientificName) {
    return commonName
  }

  if (
    normalizePestName(commonName) ===
    normalizePestName(scientificName)
  ) {
    return commonName
  }

  return `${commonName} (${scientificName})`
}