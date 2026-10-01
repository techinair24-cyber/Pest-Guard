import { useEffect, useRef, useState } from 'react'

import {
  getDeviceStatusById,
  getLatestDetection,
} from '../services/api'

import { connectDetectionSocket } from '../services/websocket'

const DEVICE_ID =
  import.meta.env.VITE_DEVICE_ID || 'FIELD-UNIT-01'

export function useLiveDetection() {
  const mountedRef = useRef(false)

  const [liveStatus, setLiveStatus] = useState({
    detection: null,
    device: null,
  })

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const updateDeviceStatus = async () => {
    try {
      const response = await getDeviceStatusById(DEVICE_ID)

      if (!mountedRef.current) {
        return
      }

      setLiveStatus((current) => ({
        ...current,
        device: response || null,
      }))

      setError(null)
    } catch (deviceError) {
      if (!mountedRef.current) {
        return
      }

      console.error(
        'Unable to update device status:',
        deviceError,
      )

      setError(deviceError)
    }
  }

  const loadInitialData = async () => {
    setLoading(true)

    try {
      const [latestResult, deviceResult] =
        await Promise.allSettled([
          getLatestDetection(),
          getDeviceStatusById(DEVICE_ID),
        ])

      if (!mountedRef.current) {
        return
      }

      if (latestResult.status === 'fulfilled') {
        setLiveStatus((current) => ({
          ...current,
          detection:
            latestResult.value?.detection || null,
        }))
      }

      if (deviceResult.status === 'fulfilled') {
        setLiveStatus((current) => ({
          ...current,
          device:
            deviceResult.value || null,
        }))
      }

      const failedResults = [
        latestResult,
        deviceResult,
      ].filter(
        (result) => result.status === 'rejected',
      )

      if (failedResults.length > 0) {
        console.error(
          'Unable to load initial live monitoring data:',
          failedResults[0].reason,
        )

        setError(failedResults[0].reason)
      } else {
        setError(null)
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true

    loadInitialData()

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
          detection: incomingDetection,
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

    const refreshTimer = window.setInterval(() => {
      updateDeviceStatus()
    }, 10000)

    return () => {
      mountedRef.current = false

      disconnect()

      window.clearInterval(refreshTimer)
    }
  }, [])

  return {
    detection: liveStatus.detection,
    device: liveStatus.device,
    loading,
    error,
  }
}