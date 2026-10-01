import { useEffect, useRef, useState } from 'react'

import {
  getDeviceStatusById,
  getLatestDetection,
} from '../services/api'

import { connectDetectionSocket } from '../services/websocket'

const DEVICE_ID =
  import.meta.env.VITE_DEVICE_ID || 'FIELD-UNIT-01'

const DEVICE_CACHE_KEY =
  'pest_guard_device_status'

function getCachedDevice() {
  try {
    const cached =
      window.localStorage.getItem(
        DEVICE_CACHE_KEY,
      )

    if (!cached) {
      return null
    }

    const device = JSON.parse(cached)

    if (!device || !device.device_id) {
      return null
    }

    return device
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

  const [liveStatus, setLiveStatus] = useState(() => ({
    detection: null,
    device: getCachedDevice(),
  }))

  const [loading, setLoading] = useState(
    () => !getCachedDevice(),
  )

  const [error, setError] = useState(null)

  const updateDeviceStatus = async () => {
    try {
      const response =
        await getDeviceStatusById(
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

      cacheDevice(response)

      setLiveStatus((current) => ({
        ...current,
        device: response,
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

      setError(deviceError)

      setLoading(false)
    }
  }

  const loadLatestDetection =
    async () => {
      try {
        const response =
          await getLatestDetection()

        if (!mountedRef.current) {
          return
        }

        setLiveStatus((current) => ({
          ...current,
          detection:
            response?.detection || null,
        }))
      } catch (detectionError) {
        if (!mountedRef.current) {
          return
        }

        console.error(
          'Unable to load latest detection:',
          detectionError,
        )

        /*
         * A failed latest-detection request must
         * never mark the real device offline.
         */
      }
    }

  const loadInitialData = async () => {
    /*
     * Device status and latest detection are
     * intentionally loaded independently.
     */
    await Promise.allSettled([
      updateDeviceStatus(),
      loadLatestDetection(),
    ])
  }

  useEffect(() => {
    mountedRef.current = true

    loadInitialData()

    /*
     * Refresh latest detection every 10 seconds.
     */
    const detectionRefreshTimer =
      window.setInterval(() => {
        loadLatestDetection()
      }, 10000)

    /*
     * Refresh the real device status every 5 seconds.
     */
    const deviceRefreshTimer =
      window.setInterval(() => {
        updateDeviceStatus()
      }, 5000)

    const disconnect =
      connectDetectionSocket(
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
            detection:
              incomingDetection,
          }))

          setError(null)

          /*
           * Refresh real device state immediately
           * after a new detection.
           */
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
    detection:
      liveStatus.detection,

    device:
      liveStatus.device,

    loading,

    error,
  }
}