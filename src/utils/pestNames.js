export function normalizePestName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

const VALID_RISKS = ['HIGH', 'MEDIUM', 'LOW', 'NO_RISK']

function precautionaryRisk() {
  return {
    risk: 'LOW',
    source: null,
    sourceUrl: null,
    rationale:
      'Please verify the insect identification before treatment. LOW is a precautionary default.',
  }
}

function unconfirmedRisk() {
  return {
    risk: 'UNCONFIRMED',
    source: null,
    sourceUrl: null,
    rationale: 'Risk is not assigned to an unverified species candidate.',
  }
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
      risk: String(item?.risk || '').toUpperCase(),
    }
    const aliases = Array.isArray(item?.aliases) ? item.aliases : []

    ;[name, scientificName, entry.pestId, ...aliases].forEach(
      (candidate) => {
        const key = normalizePestName(candidate)
        if (key) directory[key] = entry
      },
    )
  })

  return directory
}

export function getPestRiskEstimate(pest, directory = {}) {
  const key = normalizePestName(pest)

  if (!key) return precautionaryRisk()

  const catalogRisk = String(
    directory[key]?.risk || '',
  ).toUpperCase()

  if (VALID_RISKS.includes(catalogRisk)) {
    return {
      risk: catalogRisk,
      source: 'Pest Guard pest catalogue',
      rationale:
        'Risk category recorded in the matching pest catalogue entry.',
    }
  }

  return precautionaryRisk()
}

export function getDetectionRiskEstimate(
  detection,
  directory = {},
) {
  return getCandidateRiskEstimate(detection?.pest, detection, directory)
}

export function getCandidateRiskEstimate(
  candidate,
  detection,
  directory = {},
) {
  const candidateName =
    typeof candidate === 'string'
      ? candidate.trim()
      : String(candidate?.pest || '').trim()

  const pestId = String(detection?.pest_id || '').trim()

  // Never assign risk to unverified detections.
  if (
    !candidateName ||
    detection?.status !== 'HARMFUL_PEST' ||
    detection?.pest_verified !== true ||
    !pestId
  ) {
    return unconfirmedRisk()
  }

  const candidateKey = normalizePestName(candidateName)
  const pestKey = normalizePestName(detection?.pest)
  const commonKey = normalizePestName(detection?.common_name)
  const scientificKey = normalizePestName(
    detection?.scientific_name,
  )

  const catalogRecord = directory[normalizePestName(pestId)]
  const candidateRecord = directory[candidateKey]
  const detectionRecord = directory[pestKey]

  // Candidate must match the verified detection identity.
  const identityMatches =
    candidateKey === pestKey ||
    candidateKey === commonKey ||
    candidateKey === scientificKey ||
    candidateRecord?.pestId === pestId

  if (!identityMatches) {
    return unconfirmedRisk()
  }

  // Reject conflicting local catalogue identities.
  if (
    (catalogRecord && catalogRecord.pestId !== pestId) ||
    (candidateRecord && candidateRecord.pestId !== pestId) ||
    (detectionRecord && detectionRecord.pestId !== pestId)
  ) {
    return unconfirmedRisk()
  }

  const serverRisk = String(
    detection?.risk || '',
  ).trim().toUpperCase()

  const serverRationale = String(
    detection?.risk_rationale || '',
  ).trim()

  // Prefer the backend's catalogue-verified risk.
  // Do not treat a precautionary LOW default as verified.
  if (
    VALID_RISKS.includes(serverRisk) &&
    serverRationale ===
      'Risk category recorded in the matching pest catalogue entry.'
  ) {
    return {
      risk: serverRisk,
      source: 'Pest Guard pest catalogue',
      sourceUrl: detection?.metadata_source_url || null,
      rationale: serverRationale,
    }
  }

  // Fallback to the validated local catalogue.
  if (catalogRecord?.pestId === pestId) {
    const catalogRisk = String(
      catalogRecord.risk || '',
    ).trim().toUpperCase()

    if (VALID_RISKS.includes(catalogRisk)) {
      return {
        risk: catalogRisk,
        source: 'Pest Guard pest catalogue',
        sourceUrl: null,
        rationale:
          'Risk category recorded in the matching pest catalogue entry.',
      }
    }
  }

  return unconfirmedRisk()
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

  if (!scientificName) return commonName

  if (
    normalizePestName(commonName) ===
    normalizePestName(scientificName)
  ) {
    return commonName
  }

  return `${commonName} (${scientificName})`
}

export function getVerifiedDetectionDisplayName(
  detection,
  directory = {},
) {
  const pestId = String(detection?.pest_id || '').trim()

  if (
    detection?.status !== 'HARMFUL_PEST' ||
    detection?.pest_verified !== true ||
    !pestId
  ) {
    return 'Unknown pest'
  }

  const catalogEntry = directory[normalizePestName(pestId)]
  if (catalogEntry && catalogEntry.pestId !== pestId) {
    return 'Unknown pest'
  }

  const commonName = String(
    detection.common_name ||
      catalogEntry?.commonName ||
      detection.pest ||
      '',
  ).trim()
  if (!commonName) return 'Unknown pest'

  return getDisplayPestName(commonName, directory, {
    common_name: commonName,
    scientific_name:
      detection.scientific_name || catalogEntry?.scientificName || '',
  })
}
