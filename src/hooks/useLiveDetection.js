import { useEffect, useRef, useState } from 'react'

import {
  getDeviceStatusById,
  getLatestDetection,
} from '../services/api'

import { connectDetectionSocket } from '../services/websocket'
import { isNewerDetection } from '../utils/detectionHistory'

const DEVICE_ID =
  import.meta.env.VITE_DEVICE_ID || 'FIELD-UNIT-01'

const DEVICE_CACHE_KEY =
  'pest_guard_device_status'

const DEVICE_STATUS_STALE_MS = 60 * 1000

function normalizeDevice(device) {
  return device || null
}

function getCachedDevice() {
  try {
    const cached = window.localStorage.getItem(
      DEVICE_CACHE_KEY,
    )

    if (!cached) {
      return null
    }

    const device = JSON.parse(cached)

    if (!device || !device.device_id) {
      return null
    }

    return {
      ...device,
      status: 'OFFLINE',
      connection: 'DISCONNECTED',
    }
  } catch {
    return null
  }
}

function cacheDevice(device) {
  if (!device) {
    return
  }

  try {
    window.localStorage.setItem(
      DEVICE_CACHE_KEY,
      JSON.stringify(device),
    )
  } catch {
    // Ignore storage failures.
  }
}

export function useLiveDetection() {
  const mountedRef = useRef(false)
  const lastDeviceStatusSuccessAtRef = useRef(null)

  const [liveStatus, setLiveStatus] = useState(() => ({
    detection: null,
    device: getCachedDevice(),
  }))

  const [loading, setLoading] = useState(() => {
    return !getCachedDevice()
  })

  const [error, setError] = useState(null)

  const updateDeviceStatus = async () => {
    try {
      const response = await getDeviceStatusById(
        DEVICE_ID,
      )

      if (!mountedRef.current) {
        return
      }

      if (!response) {
        throw new Error(
          'Pest Guard device status was empty.',
        )
      }

      const normalizedDevice = normalizeDevice(
        response,
      )
      lastDeviceStatusSuccessAtRef.current = performance.now()

      cacheDevice(normalizedDevice)

      setLiveStatus((current) => ({
        ...current,
        device: normalizedDevice,
      }))

      setError(null)
      setLoading(false)
    } catch (deviceError) {
      if (!mountedRef.current) {
        return
      }

      console.error(
        'Unable to update device status:',
        deviceError,
      )

      setLiveStatus((current) => {
        if (!current.device) {
          return current
        }

        const lastSuccessAt = lastDeviceStatusSuccessAtRef.current
        const statusIsStale =
          lastSuccessAt === null ||
          performance.now() - lastSuccessAt > DEVICE_STATUS_STALE_MS
        const refreshedDevice = statusIsStale
          ? {
              ...current.device,
              status: 'OFFLINE',
              connection: 'DISCONNECTED',
            }
          : current.device

        cacheDevice(refreshedDevice)

        return {
          ...current,
          device: refreshedDevice,
        }
      })

      setError(deviceError)
      setLoading(false)
    }
  }

  const loadLatestDetection = async () => {
    try {
      const response = await getLatestDetection()

      if (!mountedRef.current) {
        return
      }

      setLiveStatus((current) => ({
        ...current,
        detection: isNewerDetection(response, current.detection)
          ? response
          : current.detection,
      }))
    } catch (detectionError) {
      if (!mountedRef.current) {
        return
      }

      console.error(
        'Unable to load latest detection:',
        detectionError,
      )
    }
  }

  const loadInitialData = async () => {
    await Promise.allSettled([
      updateDeviceStatus(),
      loadLatestDetection(),
    ])
  }

  useEffect(() => {
    mountedRef.current = true

    loadInitialData()

    const detectionRefreshTimer = window.setInterval(
      () => {
        loadLatestDetection()
      },
      10000,
    )

    const deviceRefreshTimer = window.setInterval(
      () => {
        updateDeviceStatus()
      },
      2000,
    )

    const disconnect = connectDetectionSocket(
      async (incomingDetection) => {
        if (!mountedRef.current) {
          return
        }

        if (!incomingDetection) {
          return
        }

        console.log(
          'New Pest Guard detection:',
          incomingDetection,
        )

        setLiveStatus((current) => ({
          ...current,
          detection: isNewerDetection(incomingDetection, current.detection)
            ? incomingDetection
            : current.detection,
        }))

        setError(null)

        await updateDeviceStatus()
      },
      (socketState) => {
        if (!mountedRef.current) {
          return
        }

        if (socketState === 'error') {
          console.error(
            'Detection WebSocket error',
          )
        }
      },
    )

    return () => {
      mountedRef.current = false
      disconnect()

      window.clearInterval(
        detectionRefreshTimer,
      )

      window.clearInterval(
        deviceRefreshTimer,
      )
    }
  }, [])

  return {
    detection: liveStatus.detection,
    device: liveStatus.device,
    loading,
    error,
  }
}