export function getDetectionTime(item) {
  return item?.detected_at || item?.timestamp || item?.created_at || null
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
