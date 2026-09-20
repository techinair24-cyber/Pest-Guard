import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getDeviceStatusById,
  getLatestDetection,
} from '../services/api'

import {
  connectDetectionSocket,
} from '../services/websocket'

export function useLiveDetection() {
  const deviceId =
    import.meta.env.VITE_DEVICE_ID || 'FIELD-UNIT-01'

  const [liveStatus, setLiveStatus] = useState({
    detection: null,
    device: null,
  })

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const mountedRef = useRef(false)

  const updateDeviceStatus = useCallback(async () => {
    try {
      const device = await getDeviceStatusById(deviceId)

      if (!mountedRef.current) {
        return
      }

      setLiveStatus((current) => ({
        ...current,
        device,
      }))

      setError(null)
    } catch (deviceError) {
      if (!mountedRef.current) {
        return
      }

      console.error(
        'Unable to get device status:',
        deviceError
      )

      setLiveStatus((current) => ({
        ...current,
        device: null,
      }))
    }
  }, [deviceId])

  const loadInitialData = useCallback(async () => {
    if (!mountedRef.current) {
      return
    }

    setLoading(true)
    setError(null)

    const [detectionResult, deviceResult] =
      await Promise.allSettled([
        getLatestDetection(),
        getDeviceStatusById(deviceId),
      ])

    if (!mountedRef.current) {
      return
    }

    const detection =
      detectionResult.status === 'fulfilled'
        ? detectionResult.value
        : null

    const device =
      deviceResult.status === 'fulfilled'
        ? deviceResult.value
        : null

    setLiveStatus({
      detection,
      device,
    })

    const detectionFailed =
      detectionResult.status === 'rejected'

    const deviceFailed =
      deviceResult.status === 'rejected'

    if (detectionFailed && deviceFailed) {
      setError('Live data unavailable')
    } else if (deviceFailed) {
      setError('Device status unavailable')
    } else {
      setError(null)
    }

    setLoading(false)
  }, [deviceId])

  useEffect(() => {
    mountedRef.current = true

    loadInitialData()

    /*
      WebSocket:
      Backend → WebSocket → this hook → Home page

      Whenever the AI/backend creates a new detection,
      the Home page receives it without refreshing.
    */

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
          incomingDetection
        )

        setLiveStatus((current) => ({
          ...current,
          detection: incomingDetection,
        }))

        setError(null)

        /*
          Refresh device information too.
          This keeps ONLINE/OFFLINE status current.
        */
        await updateDeviceStatus()
      },

      (socketError) => {
        if (!mountedRef.current) {
          return
        }

        console.error(
          'Detection WebSocket error:',
          socketError
        )
      }
    )

    /*
      Also refresh the device status periodically.
      This is useful if the field unit disconnects
      without sending a WebSocket event.
    */

    const deviceRefreshInterval = window.setInterval(
      () => {
        updateDeviceStatus()
      },
      10000
    )

    return () => {
      mountedRef.current = false

      disconnect()

      window.clearInterval(
        deviceRefreshInterval
      )
    }
  }, [
    loadInitialData,
    updateDeviceStatus,
  ])

  return {
    detection: liveStatus.detection,
    device: liveStatus.device,
    loading,
    error,
  }
}