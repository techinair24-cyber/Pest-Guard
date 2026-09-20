export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const headers = {
    ...(options.body
      ? { 'Content-Type': 'application/json' }
      : {}),
    ...(options.headers || {}),
  }

  let response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
    })
  } catch (error) {
    throw new Error(
      `Unable to connect to Pest Guard backend: ${error.message}`,
    )
  }

  let data = null

  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const message =
      data?.detail ||
      data?.message ||
      `Backend request failed with status ${response.status}`

    throw new Error(message)
  }

  return data
}

/* =========================================================
   HEALTH
========================================================= */

export const getHealth = () =>
  request('/api/health')

/* =========================================================
   DEVICES
========================================================= */

export const getDeviceStatus = async () => {
  const data = await request('/api/devices')
  return data.devices || []
}

export const getDeviceStatusById = async (deviceId) => {
  const data = await request(
    `/api/devices/${encodeURIComponent(deviceId)}`,
  )

  return data.device || null
}

export const sendDeviceHeartbeat = (
  deviceId,
  payload,
) =>
  request(
    `/api/devices/${encodeURIComponent(deviceId)}/heartbeat`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )

/* =========================================================
   DETECTIONS
========================================================= */

export const getLatestDetection = async () => {
  const data = await request('/api/detections/latest')

  return data.detection || null
}

export const getDetectionHistory = async (params = {}) => {
  const query = new URLSearchParams()

  if (params.page) {
    query.set('page', params.page)
  }

  if (params.limit) {
    query.set('limit', params.limit)
  }

  if (params.deviceId) {
    query.set('device_id', params.deviceId)
  }

  if (params.pest) {
    query.set('pest', params.pest)
  }

  if (params.status) {
    query.set('status', params.status)
  }

  if (params.dateFrom) {
    query.set('date_from', params.dateFrom)
  }

  if (params.dateTo) {
    query.set('date_to', params.dateTo)
  }

  const queryString = query.toString()

  const data = await request(
    `/api/detections${
      queryString ? `?${queryString}` : ''
    }`,
  )

  return data
}

/* =========================================================
   CREATE DETECTION
========================================================= */

export const sendDetection = (payload) =>
  request('/api/device/detection', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

/* =========================================================
   PESTS
========================================================= */

export const getPests = async () => {
  const data = await request('/api/pests')
  return data.pests || []
}

export const getPestInfo = async (pestId) =>
  request(
    `/api/pests/${encodeURIComponent(pestId)}`,
  )

export const getPestById = getPestInfo

/* =========================================================
   SOLUTIONS
========================================================= */

export const getSolutions = async () => {
  const data = await request('/api/solutions')
  return data.solutions || []
}

export const getSolution = async (pestId) =>
  request(
    `/api/solutions/${encodeURIComponent(pestId)}`,
  )

export const getSolutionByPest = getSolution

export const predictAI = (audio) =>
  request('/api/ai/predict', {
    method: 'POST',
    body: JSON.stringify({ audio }),
  })