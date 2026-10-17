export function getDetectionTime(item) {
  return item?.detected_at || item?.timestamp || item?.created_at || null
}

export function isNewerDetection(candidate, current) {
  if (!candidate) {
    return false
  }

  if (!current) {
    return true
  }

  const candidateTime = parseServerTimestamp(getDetectionTime(candidate))
  const currentTime = parseServerTimestamp(getDetectionTime(current))

  if (Number.isFinite(candidateTime) && Number.isFinite(currentTime)) {
    if (candidateTime !== currentTime) {
      return candidateTime > currentTime
    }
  } else if (Number.isFinite(candidateTime)) {
    return true
  } else if (Number.isFinite(currentTime)) {
    return false
  }

  const candidateId = Number(candidate.id)
  const currentId = Number(current.id)
  if (Number.isFinite(candidateId) && Number.isFinite(currentId)) {
    return candidateId > currentId
  }

  return false
}

export function selectNewerDetection(current, candidate) {
  return isNewerDetection(candidate, current) ? candidate : current
}

export function isLatestDetectionCandidate(item, deviceId, now = Date.now()) {
  const timestamp = parseServerTimestamp(getDetectionTime(item))
  const sameDevice =
    !deviceId || !item?.device_id || item.device_id === deviceId
  const hasPestName =
    typeof item?.pest === 'string' && item.pest.trim() !== ''
  const status = String(item?.status || '').toUpperCase()
  const identificationStatus = String(
    item?.identification_status || '',
  ).toUpperCase()
  const commonName = String(item?.common_name || '').trim().toLowerCase()
  const isDetectionEvent =
    hasPestName ||
    ['HARMFUL_PEST', 'NON_PEST', 'UNKNOWN'].includes(status) ||
    identificationStatus === 'UNCONFIRMED' ||
    identificationStatus === 'ERROR' ||
    commonName === 'unidentified sound'

  return (
    Number.isFinite(timestamp) &&
    timestamp <= now + 5000 &&
    sameDevice &&
    isDetectionEvent
  )
}

export function getDetectionDisplayStatus(item) {
  if (!item) {
    return ''
  }

  const message = String(item.message || '')
  const status = String(item.status || '').toUpperCase()
  const identificationStatus = String(
    item.identification_status || '',
  ).toUpperCase()

  if (
    identificationStatus === 'ERROR' ||
    message.toUpperCase().startsWith('INFERENCE_ERROR:')
  ) {
    return 'Inference error'
  }
  if (status === 'NON_PEST') {
    return 'Non-pest sound'
  }
  if (identificationStatus === 'CONFIRMED') {
    return 'Confirmed pest identification'
  }
  if (item.pest) {
    return 'Possible match - not confirmed'
  }
  return 'Rejected or uncertain classification'
}

export function parseServerTimestamp(value) {
  if (!value) {
    return NaN
  }

  const text = String(value).trim()

  if (!text) {
    return NaN
  }

  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)
  const normalized = hasTimezone ? text : `${text}Z`
  const timestamp = new Date(normalized).getTime()

  return Number.isFinite(timestamp) ? timestamp : NaN
}

export function isAfterHistoryClear(item, clearedAt) {
  if (!clearedAt) {
    return true
  }

  const clearedAtMs = parseServerTimestamp(clearedAt)
  const detectionTimeMs = parseServerTimestamp(getDetectionTime(item))

  if (!Number.isFinite(clearedAtMs)) {
    return true
  }

  return Number.isFinite(detectionTimeMs) && detectionTimeMs > clearedAtMs
}

function sameDetection(first, second) {
  if (first?.id != null && second?.id != null) {
    return String(first.id) === String(second.id)
  }

  const firstTime = parseServerTimestamp(getDetectionTime(first))
  const secondTime = parseServerTimestamp(getDetectionTime(second))

  return Number.isFinite(firstTime) && firstTime === secondTime
}

function sortNewestFirst(detections) {
  return detections.sort((first, second) => {
    const firstTime = parseServerTimestamp(getDetectionTime(first))
    const secondTime = parseServerTimestamp(getDetectionTime(second))

    if (!Number.isFinite(firstTime) && !Number.isFinite(secondTime)) return 0
    if (!Number.isFinite(firstTime)) return 1
    if (!Number.isFinite(secondTime)) return -1
    return secondTime - firstTime
  })
}

export function mergeDetections(...groups) {
  const merged = []

  groups.flat().forEach((detection) => {
    if (!merged.some((existing) => sameDetection(existing, detection))) {
      merged.push(detection)
    }
  })

  return sortNewestFirst(merged)
}
